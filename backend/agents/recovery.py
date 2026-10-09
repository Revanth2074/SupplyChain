"""
Recovery Analysis Agent.
Projects the recovery timeline for the chosen strategy (ML counterfactual), cohort recovery
percentiles, supplier-change probability, milestones and resilience actions.
"""

from __future__ import annotations

import time

import numpy as np

from agents.prediction import registry
from agents.state import done, emit
from services.data_store import store


def recovery_node(state: dict) -> dict:
    """LangGraph node (Recovery agent)."""
    t0 = time.time()
    emit("agent_start", "recovery")
    incident, plan, pred = state["incident"], state["plan"], state["impact"]["prediction"]
    primary = plan.get("primary_strategy")
    cf_pred = registry.predict({**incident, "response_type": primary})
    df = store.df
    coh = df[(df["disruption_type"] == incident["disruption_type"]) & (df["response_type"] == primary)]
    if incident.get("disruption_severity"):
        c2 = coh[coh["disruption_severity"] == int(incident["disruption_severity"])]
        coh = c2 if len(c2) > 50 else coh
    pct = {f"p{q}": float(np.percentile(coh["full_recovery_days"], q)) for q in (10, 25, 50, 75, 90)} if len(coh) else {}
    part = float(cf_pred["partial_recovery_days"])
    full = float(cf_pred["full_recovery_days"])
    rt = int(incident.get("response_time_days") or 2)
    milestones = [
        {"day": 0, "label": "Disruption detected"},
        {"day": rt, "label": f"{primary} response initiated"},
        {"day": round(part), "label": "Partial recovery (≈ production stabilised)"},
        {"day": round((part + full) / 2), "label": "Ramp-up to normal capacity"},
        {"day": round(full), "label": "Full recovery"},
    ]
    resilience_actions = []
    if not incident.get("has_backup_supplier"):
        resilience_actions.append("Qualify a backup supplier — historically reduces full recovery time by ~25-30%")
    if int(incident.get("supplier_tier") or 1) >= 2:
        resilience_actions.append("Extend visibility to Tier 2/3 suppliers (sub-tier mapping & early warning)")
    if incident.get("supplier_size") == "Small":
        resilience_actions.append("Diversify away from single small suppliers for critical parts")
    resilience_actions.append("Hold strategic inventory buffer sized to the P75 partial-recovery window")
    recovery = {"strategy": primary, "predicted_partial_days": round(part), "predicted_full_days": round(full),
                "predicted_revenue_loss": cf_pred["revenue_loss_usd"], "cohort_size": int(len(coh)),
                "ranges": cf_pred["ranges"], "support": cf_pred["support"],
                "cohort_full_recovery_percentiles": pct,
                "supplier_change_probability": round(float(coh["permanent_supplier_change"].mean()), 3) if len(coh) else None,
                "milestones": milestones, "resilience": pred["resilience_score"],
                "resilience_actions": resilience_actions}
    summ = f"Partial ≈{round(part)}d, full ≈{round(full)}d with {primary} (cohort P50 {pct.get('p50', 0):.0f}d, n={len(coh)})"
    return {"recovery": recovery, "trace": [done("recovery", t0, summ, recovery)]}
