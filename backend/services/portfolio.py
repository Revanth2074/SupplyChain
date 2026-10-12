"""Supplier portfolio risk: score a list of suppliers against every disruption type,
weighted by how often each type hits suppliers in that region, and summarise as a
region x tier heatmap plus a ranked list of the riskiest suppliers."""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

from services.data_store import store
from agents.precedent import estimator

REQUIRED = ["supplier_name", "industry", "supplier_region", "supplier_tier", "supplier_size", "has_backup_supplier"]
# Optional operational columns (your own supplier data, not part of the historical dataset).
# Defaults are neutral so a minimal CSV still works.
OPTIONAL = {
    "inventory_days": 21.0,          # days of stock cover held for this supplier's parts
    "dependency_pct": 0.5,           # share of the part's volume sourced from this supplier (0-1)
    "on_time_rate": 0.95,            # on-time-in-full delivery rate over the last 12 months (0-1)
    "recent_disruptions": 0,         # disruptions with this supplier in the last 12 months
    "annual_spend_usd": 5_000_000.0,
    "products": "",                  # ';'-separated products this supplier feeds
}
# Sample portfolio (demo data): name, industry, region, tier, size, backup,
# inventory_days, dependency_pct, on_time_rate, recent_disruptions, annual_spend_usd, products
SAMPLE = [
    ("Shenzhen MicroParts", "Electronics", "Asia-Pacific", 2, "Medium", False, 9, 0.85, 0.88, 3, 14e6, "Control Unit;Sensor Pack"),
    ("Bavaria Brake Systems", "Automotive", "Europe", 1, "Large", True, 28, 0.55, 0.97, 0, 22e6, "Brake Module"),
    ("Ohio Precision Castings", "Automotive", "North America", 2, "Small", False, 12, 0.9, 0.91, 2, 6e6, "Brake Module;Housing"),
    ("Penang Wafer Services", "Electronics", "Asia-Pacific", 3, "Small", False, 6, 1.0, 0.86, 4, 9e6, "Control Unit"),
    ("Lyon Pharma API", "Pharmaceuticals", "Europe", 1, "Medium", False, 35, 0.8, 0.96, 1, 18e6, "API Batch"),
    ("Hyderabad Generics", "Pharmaceuticals", "Asia-Pacific", 2, "Large", True, 40, 0.45, 0.94, 1, 11e6, "API Batch;Packaging Kit"),
    ("Toulouse Avionics", "Aerospace", "Europe", 1, "Large", True, 30, 0.6, 0.97, 0, 26e6, "Avionics Suite"),
    ("Kansas Composite Works", "Aerospace", "North America", 2, "Medium", False, 14, 0.95, 0.9, 2, 12e6, "Airframe Panel"),
    ("Sao Paulo Packaging", "Consumer Goods", "South America", 1, "Medium", True, 25, 0.5, 0.95, 1, 4e6, "Packaging Kit"),
    ("Dubai Logistics Hub", "Consumer Goods", "Africa/Middle East", 2, "Large", False, 18, 0.7, 0.92, 2, 7e6, "Packaging Kit;Housing"),
    ("Monterrey Harness Co", "Automotive", "North America", 1, "Medium", True, 22, 0.5, 0.96, 0, 8e6, "Wiring Harness"),
    ("Taipei Display Glass", "Electronics", "Asia-Pacific", 1, "Large", True, 20, 0.6, 0.97, 0, 16e6, "Display Panel"),
    ("Johannesburg Metals", "Automotive", "Africa/Middle East", 3, "Medium", False, 16, 0.75, 0.89, 3, 5e6, "Housing"),
    ("Santiago Lithium", "Electronics", "South America", 3, "Small", False, 10, 1.0, 0.87, 2, 6e6, "Battery Cell"),
    ("Basel Biologics", "Pharmaceuticals", "Europe", 2, "Small", False, 20, 0.9, 0.93, 1, 7e6, "API Batch"),
    ("Quebec Titanium", "Aerospace", "North America", 3, "Medium", True, 45, 0.4, 0.98, 0, 9e6, "Airframe Panel"),
    ("Ho Chi Minh Textiles", "Consumer Goods", "Asia-Pacific", 2, "Small", False, 11, 0.8, 0.9, 2, 3e6, "Seat Fabric"),
    ("Rotterdam Chemicals", "Pharmaceuticals", "Europe", 3, "Large", True, 32, 0.5, 0.96, 0, 10e6, "API Batch;Packaging Kit"),
]
COLUMNS = REQUIRED + list(OPTIONAL)


def sample_csv() -> str:
    return pd.DataFrame(SAMPLE, columns=COLUMNS).to_csv(index=False)


def parse_csv(text: str) -> list[dict]:
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing columns: {', '.join(missing)}")
    df["has_backup_supplier"] = df["has_backup_supplier"].astype(str).str.strip().str.lower().isin(
        ["true", "yes", "y", "1"])
    for col, default in OPTIONAL.items():
        if col not in df.columns:
            df[col] = default
        df[col] = df[col].fillna(default)
        if col != "products":
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(default)
    df["products"] = df["products"].astype(str).replace("nan", "")
    return df[COLUMNS].to_dict("records")


def rows_or_sample(csv: str | None) -> list[dict]:
    return parse_csv(csv) if csv and csv.strip() else parse_csv(sample_csv())


def _validate(rows: list[dict]) -> list[str]:
    opts = store.options()
    errs = []
    for i, r in enumerate(rows, 1):
        for k in ("industry", "supplier_region", "supplier_size"):
            if r.get(k) not in opts.get(k, []):
                errs.append(f"row {i} ({r.get('supplier_name')}): {k} '{r.get(k)}' not one of {opts.get(k)}")
        try:
            if int(r.get("supplier_tier")) not in (1, 2, 3, 4):
                raise ValueError
        except (TypeError, ValueError):
            errs.append(f"row {i} ({r.get('supplier_name')}): supplier_tier must be 1, 2, 3 or 4")
    return errs


def score(rows: list[dict], severity: int = 3) -> dict:
    if not rows:
        raise ValueError("No suppliers provided")
    if len(rows) > 500:
        raise ValueError("At most 500 suppliers per request")
    errs = _validate(rows)
    if errs:
        raise ValueError("; ".join(errs[:8]))
    df = store.df
    types = sorted(df["disruption_type"].unique())
    # how often each disruption type hits suppliers in a region (exposure weights)
    mix = (df.groupby(["supplier_region", "disruption_type"]).size()
           .groupby(level=0).transform(lambda s: s / s.sum()))
    grid = [{**r, "supplier_tier": int(r["supplier_tier"]), "disruption_type": t, "disruption_severity": severity}
            for r in rows for t in types]
    pred = estimator.predict_batch(grid)
    pred["supplier_idx"] = np.repeat(np.arange(len(rows)), len(types))
    pred["disruption_type"] = types * len(rows)
    pred["weight"] = [float(mix.get((r["supplier_region"], t), 1 / len(types))) for r, t in
                      ((rows[i], t) for i in range(len(rows)) for t in types)]

    out = []
    for i, r in enumerate(rows):
        p = pred[pred["supplier_idx"] == i]
        w = p["weight"] / p["weight"].sum()
        exp = {k: float((p[k] * w).sum()) for k in ("risk_probability", "revenue_loss_usd",
                                                     "full_recovery_days", "production_impact_pct")}
        worst = p.sort_values("revenue_loss_usd", ascending=False).iloc[0]
        res = estimator.resilience(r, {"full_recovery_days": exp["full_recovery_days"],
                                      "production_impact_pct": exp["production_impact_pct"]})
        risk_index = round(100 * (0.6 * exp["risk_probability"] + 0.4 * (1 - res["score"] / 100)), 1)
        drivers = []
        if not r["has_backup_supplier"]:
            drivers.append("No backup supplier")
        if int(r["supplier_tier"]) >= 2:
            drivers.append(f"Tier {r['supplier_tier']} visibility")
        if r["supplier_size"] == "Small":
            drivers.append("Small supplier")
        if exp["risk_probability"] >= 0.6:
            drivers.append(f"High-impact profile for {r['industry']}")
        out.append({
            **r, "risk_index": risk_index,
            "band": "Critical" if risk_index >= 70 else "High" if risk_index >= 55 else
                    "Medium" if risk_index >= 40 else "Low",
            "expected_risk_probability": round(exp["risk_probability"], 3),
            "expected_revenue_loss_usd": round(exp["revenue_loss_usd"], 0),
            "expected_full_recovery_days": round(exp["full_recovery_days"], 1),
            "expected_production_impact_pct": round(exp["production_impact_pct"], 1),
            "resilience": res, "drivers": drivers,
            "worst_case": {"disruption_type": worst["disruption_type"],
                           "revenue_loss_usd": round(float(worst["revenue_loss_usd"]), 0),
                           "full_recovery_days": round(float(worst["full_recovery_days"]), 0)},
            "by_type": [{"disruption_type": t, "risk_probability": round(float(x["risk_probability"]), 3),
                         "revenue_loss_usd": round(float(x["revenue_loss_usd"]), 0),
                         "full_recovery_days": round(float(x["full_recovery_days"]), 0),
                         "weight": round(float(x["weight"]), 3)} for t, (_, x) in zip(types, p.iterrows())],
        })
    out.sort(key=lambda s: -s["risk_index"])
    for rank, s in enumerate(out, 1):
        s["rank"] = rank

    regions = sorted({s["supplier_region"] for s in out})
    heat = []
    for reg in regions:
        for tier in (1, 2, 3, 4):
            cell = [s for s in out if s["supplier_region"] == reg and s["supplier_tier"] == tier]
            heat.append({"region": reg, "tier": tier, "suppliers": len(cell),
                         "avg_risk_index": round(sum(s["risk_index"] for s in cell) / len(cell), 1) if cell else None,
                         "names": [s["supplier_name"] for s in cell]})
    return {
        "count": len(out), "severity_assumed": severity, "disruption_types": types,
        "summary": {
            "avg_risk_index": round(sum(s["risk_index"] for s in out) / len(out), 1),
            "critical_or_high": sum(s["band"] in ("Critical", "High") for s in out),
            "without_backup": sum(not s["has_backup_supplier"] for s in out),
            "expected_loss_total": round(sum(s["expected_revenue_loss_usd"] for s in out), 0),
        },
        "heatmap": {"regions": regions, "tiers": [1, 2, 3, 4], "cells": heat},
        "suppliers": out,
    }
