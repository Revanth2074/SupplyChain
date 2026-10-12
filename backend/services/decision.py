"""Decision support: scenario comparison with mitigation cost vs avoided loss (ROI), and
root-cause / disruption-propagation analysis.

Recovery times and production impact per scenario come from the ML models (trained on 100k cases).
Business loss: the ML revenue-loss estimate is the do-nothing baseline; every scenario's loss is that
baseline scaled by how long (and how badly) it leaves you short of supply - its *effective outage days*
(full outage until partial recovery, then half until full recovery) times its production impact.
In the historical data the response strategy mainly changes recovery time, not the recorded loss,
so scaling by outage is what makes the scenarios comparable. Mitigation costs are *assumptions*
(editable per request) because the dataset has no cost data."""
from __future__ import annotations

from services.data_store import store
from agents.precedent import estimator

# Cost model per response: fixed set-up cost + running cost per day until full recovery (USD).
DEFAULT_COSTS = {
    "do_nothing": {"fixed": 0, "daily": 2_000, "note": "customer service, expediting and penalties"},
    "backup": {"fixed": 60_000, "daily": 2_500, "note": "switch volumes to the qualified backup, price premium"},
    "alt_supplier": {"fixed": 120_000, "daily": 3_000, "note": "spot qualification, premium pricing, air freight"},
    "reroute": {"fixed": 150_000, "daily": 4_000, "note": "line changeover, extra logistics between plants"},
    "buffer": {"fixed": 40_000, "daily": 1_500, "note": "release safety stock, replenishment holding cost"},
    "combined": {"fixed": 220_000, "daily": 5_000, "note": "parallel alt-sourcing, buffer release and rerouting"},
}

SCENARIOS = [
    ("do_nothing", "Absorb it: delay customer orders", {"response_type": "Customer Delay"}),
    ("backup", "Activate the backup supplier", {"response_type": "Alternative Supplier", "has_backup_supplier": True}),
    ("alt_supplier", "Spot-buy from an alternative supplier", {"response_type": "Alternative Supplier", "has_backup_supplier": False}),
    ("reroute", "Reroute production to another line", {"response_type": "Production Reroute"}),
    ("buffer", "Release the inventory buffer", {"response_type": "Inventory Buffer"}),
    ("combined", "Run the combined playbook", {"response_type": "Combined Strategy"}),
]


def compare_scenarios(incident: dict, costs: dict | None = None) -> dict:
    """Each scenario = the same disruption handled a different way. Baseline = absorb it."""
    costs = {k: {**v, **(costs or {}).get(k, {})} for k, v in DEFAULT_COSTS.items()}
    inc = {**incident}
    inc.setdefault("response_time_days", 2)
    rows = []
    preds = [(key, label, change, estimator.predict({**inc, **change}, keep=tuple(change), pair={**inc, **SCENARIOS[0][2]}))
             for key, label, change in SCENARIOS]
    outage = lambda p: p["partial_recovery_days"] + 0.5 * max(0.0, p["full_recovery_days"] - p["partial_recovery_days"])
    b = preds[0][3]
    base_exposure = max(1e-6, outage(b) * b["production_impact_pct"])
    for key, label, change, p in preds:
        c = costs[key]
        cost = float(c["fixed"]) + float(c["daily"]) * float(p["full_recovery_days"])
        scale = outage(p) * p["production_impact_pct"] / base_exposure
        rows.append({
            "key": key, "label": label, "change": change,
            "hypothetical": key == "backup" and not inc.get("has_backup_supplier"),
            "production_impact_pct": p["production_impact_pct"], "revenue_loss_usd": round(b["revenue_loss_usd"] * scale, 0),
            "model_revenue_loss_usd": p["revenue_loss_usd"], "outage_days": round(outage(p), 1),
            "partial_recovery_days": p["partial_recovery_days"], "full_recovery_days": p["full_recovery_days"],
            "risk_probability": p["risk_probability"], "ranges": p["ranges"],
            "mitigation_cost_usd": round(cost, 0), "cost_note": c["note"],
        })
    base = rows[0]
    for r in rows:
        r["avoided_loss_usd"] = round(base["revenue_loss_usd"] - r["revenue_loss_usd"], 0)
        r["extra_cost_usd"] = round(r["mitigation_cost_usd"] - base["mitigation_cost_usd"], 0)
        r["net_benefit_usd"] = round(r["avoided_loss_usd"] - r["extra_cost_usd"], 0)
        r["days_saved"] = round(base["full_recovery_days"] - r["full_recovery_days"], 0)
        r["roi"] = round(r["net_benefit_usd"] / r["extra_cost_usd"], 2) if r["extra_cost_usd"] > 0 else None
        r["total_cost_usd"] = round(r["revenue_loss_usd"] + r["mitigation_cost_usd"], 0)
    # recommend the lowest total business cost (loss + mitigation); prefer real options over hypothetical ones
    real = [r for r in rows if not r["hypothetical"]]
    best = min(real, key=lambda r: (r["total_cost_usd"], r["full_recovery_days"]))
    best_any = min(rows, key=lambda r: (r["total_cost_usd"], r["full_recovery_days"]))
    if best["key"] == "do_nothing":
        why = "None of the mitigations pays for itself for this profile, so the cheapest option is to absorb the delay."
    else:
        extra = (f"for ${best['extra_cost_usd']:,.0f} of extra cost" if best["extra_cost_usd"] > 0
                 else f"and also costs ${-best['extra_cost_usd']:,.0f} less to run")
        why = (f"{best['label']} has the lowest total business cost (loss + mitigation). It avoids "
               f"${best['avoided_loss_usd']:,.0f} of loss {extra}, a net benefit of ${best['net_benefit_usd']:,.0f}, "
               f"and recovers {best['days_saved']:.0f} days sooner than doing nothing.")
    out = {"incident": inc, "baseline": "do_nothing", "recommended": best["key"], "why": why, "scenarios": rows,
           "assumptions": costs, "support": estimator.support(inc)}
    if best_any["hypothetical"]:
        out["hint"] = (f"If you qualified a backup supplier, '{best_any['label']}' would be cheaper still "
                       f"(total ${best_any['total_cost_usd']:,.0f}).")
    return out


# ---------------------------------------------------------------- root cause / propagation
CHAINS = {
    "Port Congestion": ["Port congestion", "Shipments stuck at the port", "Raw material shortage"],
    "Labor Strike": ["Labor strike at the supplier", "Supplier output halted", "Component shortage"],
    "Cyber Attack": ["Cyber attack", "Supplier ERP and plant systems down", "Orders and shipments frozen"],
    "Natural Disaster": ["Natural disaster", "Supplier site or transport routes damaged", "Supply interruption"],
    "Geopolitical": ["Sanctions, tariffs or conflict", "Trade restricted or rerouted", "Longer lead times, blocked parts"],
    "Factory Incident": ["Factory incident at the supplier", "Supplier capacity lost", "Component shortage"],
}

FACTOR_TEXT = {
    "has_backup_supplier": lambda v: "Single source: no qualified backup supplier" if not v else "A qualified backup supplier exists",
    "disruption_severity": lambda v: f"Severity {v} of 5",
    "supplier_tier": lambda v: "Direct (Tier 1) supplier" if int(v) == 1 else f"Tier {v} sub-supplier: less visibility, longer to replace",
    "response_time_days": lambda v: f"Response started after {v} day(s)",
    "supplier_size": lambda v: f"{v} supplier ({'limited capacity buffers' if v == 'Small' else 'more capacity to recover'})",
    "industry": lambda v: f"{v} industry profile",
    "supplier_region": lambda v: f"{v} regional exposure",
    "response_type": lambda v: f"Response strategy: {v}",
    "disruption_type": lambda v: f"Disruption type: {v}",
}


def root_cause(incident: dict) -> dict:
    inc = {**incident}
    inc.setdefault("response_time_days", 2)
    p = estimator.predict(inc)
    ex = estimator.explain(inc)
    t = inc.get("disruption_type") or "Factory Incident"
    first = CHAINS.get(t, CHAINS["Factory Incident"])
    rt = int(p["inputs_used"]["response_time_days"])
    partial, full = p["partial_recovery_days"], p["full_recovery_days"]
    chain = [
        {"stage": first[0], "kind": "root cause", "when": "Day 0", "detail": f"The triggering event ({t.lower()})."},
        {"stage": first[1], "kind": "mechanism", "when": "Day 0-1", "detail": "The supplier can no longer ship normally."},
        {"stage": first[2], "kind": "supply effect", "when": f"From ~day {max(1, rt)}",
         "detail": "Inbound parts stop arriving once in-transit stock and buffers run out."},
        {"stage": "Production slowdown", "kind": "operational effect", "when": f"Until ~day {partial:.0f}",
         "detail": f"About {p['production_impact_pct']:.0f}% of production capacity is lost until partial recovery.",
         "metric": p["production_impact_pct"], "unit": "%"},
        {"stage": "Customer orders delayed", "kind": "customer effect", "when": f"Until ~day {full:.0f}",
         "detail": f"Backlog clears only at full recovery, about {full:.0f} days after the event.",
         "metric": full, "unit": "days"},
        {"stage": "Revenue loss", "kind": "financial effect", "when": "Cumulative",
         "detail": f"Expected revenue loss about ${p['revenue_loss_usd']:,.0f} "
                   f"(80% range ${p['ranges']['revenue_loss_usd']['p10']:,.0f} to ${p['ranges']['revenue_loss_usd']['p90']:,.0f}).",
         "metric": p["revenue_loss_usd"], "unit": "$"},
    ]

    def factors(target, worse_is_positive=True):
        out = []
        for c in ex[target]["local"]:
            f = c["feature"]
            if f == "disruption_type":
                continue
            delta = c["contribution"]
            out.append({"feature": f, "text": FACTOR_TEXT.get(f, lambda v: f"{f}: {v}")(c["value"]),
                        "value": c["value"], "baseline": c["baseline"], "effect": round(delta, 2)})
        return out

    rec = factors("full_recovery_days")
    imp = {f["feature"]: f["effect"] for f in factors("production_impact_pct")}
    for f in rec:
        f["impact_effect_pts"] = round(imp.get(f["feature"], 0.0), 2)
    weight = lambda f: f["effect"] + 3 * f["impact_effect_pts"]  # 1 point of impact ~ 3 days of recovery
    contributing = sorted([f for f in rec if weight(f) > 0.05], key=lambda f: -weight(f))
    mitigating = sorted([f for f in rec if weight(f) < -0.05], key=weight)

    df = store.df
    sub = df[df["disruption_type"] == t]
    if inc.get("industry"):
        sub = sub[sub["industry"] == inc["industry"]]
    evidence = {
        "cases": int(len(sub)),
        "share_high_impact": round(float((sub["production_impact_pct"] >= 50).mean()), 3) if len(sub) else None,
        "avg_full_recovery": round(float(sub["full_recovery_days"].mean()), 1) if len(sub) else None,
        "avg_loss": round(float(sub["revenue_loss_usd"].mean()), 0) if len(sub) else None,
        "backup_effect_days": round(float(sub[~sub["has_backup_supplier"]]["full_recovery_days"].mean()
                                          - sub[sub["has_backup_supplier"]]["full_recovery_days"].mean()), 1)
        if len(sub) else None,
    }
    # protective factors the model's baseline comparison cannot show (its baseline already has them)
    if inc.get("has_backup_supplier") and evidence["backup_effect_days"]:
        mitigating.insert(0, {"feature": "has_backup_supplier", "text": "A qualified backup supplier exists",
                              "detail": f"historically {evidence['backup_effect_days']:.0f} days faster full recovery",
                              "effect": -evidence["backup_effect_days"], "impact_effect_pts": 0.0})
    if rt <= 1:
        mitigating.append({"feature": "response_time_days", "text": "Fast response (within a day)", "effect": -1.0, "impact_effect_pts": 0.0})
    if inc.get("supplier_size") == "Large":
        mitigating.append({"feature": "supplier_size", "text": "Large supplier with more capacity to recover", "effect": -0.5, "impact_effect_pts": 0.0})
    if not inc.get("has_backup_supplier") and evidence["backup_effect_days"]:
        for f in contributing:
            if f["feature"] == "has_backup_supplier":
                f["detail"] = f"cases without a backup took {evidence['backup_effect_days']:.0f} days longer on average"
    return {"incident": inc, "root_cause": first[0], "chain": chain, "contributing": contributing[:6],
            "mitigating": mitigating[:4], "prediction": {k: p[k] for k in ("production_impact_pct", "revenue_loss_usd",
                                                                              "partial_recovery_days", "full_recovery_days",
                                                                              "risk_probability", "risk_level")},
            "evidence": evidence, "support": p["support"]}
