"""Supplier portfolio risk: score a list of suppliers against every disruption type,
weighted by how often each type hits suppliers in that region, and summarise as a
region x tier heatmap plus a ranked list of the riskiest suppliers."""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

from .data_store import store
from .ml_models import registry

REQUIRED = ["supplier_name", "industry", "supplier_region", "supplier_tier", "supplier_size", "has_backup_supplier"]
SAMPLE = [
    ("Shenzhen MicroParts", "Electronics", "Asia-Pacific", 2, "Medium", False),
    ("Bavaria Brake Systems", "Automotive", "Europe", 1, "Large", True),
    ("Ohio Precision Castings", "Automotive", "North America", 2, "Small", False),
    ("Penang Wafer Services", "Electronics", "Asia-Pacific", 3, "Small", False),
    ("Lyon Pharma API", "Pharmaceuticals", "Europe", 1, "Medium", False),
    ("Hyderabad Generics", "Pharmaceuticals", "Asia-Pacific", 2, "Large", True),
    ("Toulouse Avionics", "Aerospace", "Europe", 1, "Large", True),
    ("Kansas Composite Works", "Aerospace", "North America", 2, "Medium", False),
    ("Sao Paulo Packaging", "Consumer Goods", "South America", 1, "Medium", True),
    ("Dubai Logistics Hub", "Consumer Goods", "Africa/Middle East", 2, "Large", False),
    ("Monterrey Harness Co", "Automotive", "North America", 1, "Medium", True),
    ("Taipei Display Glass", "Electronics", "Asia-Pacific", 1, "Large", True),
    ("Johannesburg Metals", "Automotive", "Africa/Middle East", 3, "Medium", False),
    ("Santiago Lithium", "Electronics", "South America", 3, "Small", False),
    ("Basel Biologics", "Pharmaceuticals", "Europe", 2, "Small", False),
    ("Quebec Titanium", "Aerospace", "North America", 3, "Medium", True),
    ("Ho Chi Minh Textiles", "Consumer Goods", "Asia-Pacific", 2, "Small", False),
    ("Rotterdam Chemicals", "Pharmaceuticals", "Europe", 3, "Large", True),
]


def sample_csv() -> str:
    return pd.DataFrame(SAMPLE, columns=REQUIRED).to_csv(index=False)


def parse_csv(text: str) -> list[dict]:
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing columns: {', '.join(missing)}")
    df["has_backup_supplier"] = df["has_backup_supplier"].astype(str).str.strip().str.lower().isin(
        ["true", "yes", "y", "1"])
    return df[REQUIRED].to_dict("records")


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
    pred = registry.predict_batch(grid)
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
        res = registry.resilience(r, {"full_recovery_days": exp["full_recovery_days"],
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
