"""
Recovery Analysis Agent.
Projects the recovery timeline for the chosen strategy (precedent counterfactual), cohort recovery
percentiles, supplier-change probability, milestones and resilience actions.
"""

from __future__ import annotations

import numpy as np

from agents.base import Action, Agent, Tool
from agents.precedent import estimator
from services.data_store import store


def project_recovery(incident: dict, plan: dict, pred: dict) -> dict:
    """Counterfactual recovery timeline for the chosen strategy, cohort percentiles and resilience actions."""
    primary = plan.get("primary_strategy")
    cf_pred = estimator.predict({**incident, "response_type": primary}, keep=("response_type",))
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
    return recovery


class RecoveryAgent(Agent):
    """Goal: a recovery timeline for the chosen strategy that is consistent with what comparable cases
    actually took. Tools: the precedent counterfactual (past cases like this one handled with the chosen strategy) with cohort
    percentiles, and a consistency check of the projection against the cohort's P10-P90."""

    id, node = "recovery", "recovery"
    goal = "Project the recovery timeline for the chosen strategy and check it against the cohort"
    max_steps = 2

    def make_tools(self) -> list[Tool]:
        return [Tool("project_timeline", "Precedent estimate under the chosen strategy + cohort percentiles",
                     lambda incident, plan, prediction: project_recovery(incident, plan, prediction)),
                Tool("cohort_consistency", "Is the projected full recovery inside the cohort's P10-P90?",
                     lambda recovery: _consistency(recovery))]

    def perceive(self, state: dict) -> dict:
        return {"incident": state["incident"], "plan": state["plan"], "pred": state["impact"]["prediction"],
                "recovery": None, "check": None}

    def decide(self, obs: dict, steps: list[dict]) -> Action | None:
        if obs["recovery"] is None:
            return Action("project_timeline", {"incident": obs["incident"], "plan": obs["plan"], "prediction": obs["pred"]},
                          f"Project recovery if we execute {obs['plan'].get('primary_strategy')}")
        if obs["check"] is None:
            return Action("cohort_consistency", {"recovery": obs["recovery"]},
                          "Check the projection against what comparable cases actually took")
        return None

    def observe(self, obs: dict, action: Action, result, error: str | None) -> dict:
        if action.tool == "project_timeline":
            obs["recovery"] = result
        else:
            obs["check"] = result
        return obs

    def summarise(self, action: Action, result, error: str | None) -> str:
        if action.tool == "project_timeline":
            return f"partial {result['predicted_partial_days']} d, full {result['predicted_full_days']} d (cohort n={result['cohort_size']})"
        return result["note"]

    def reflect(self, obs: dict, steps: list[dict]) -> dict:
        r, chk = obs["recovery"], obs["check"]
        pct = r["cohort_full_recovery_percentiles"]
        summ = (f"Partial ≈{r['predicted_partial_days']}d, full ≈{r['predicted_full_days']}d with {r['strategy']} "
                f"(cohort P50 {pct.get('p50', 0):.0f}d, n={r['cohort_size']})" + ("" if chk["inside"] else " · outside cohort range"))
        return {"status": "done" if chk["inside"] else "partial", "confidence": 0.85 if chk["inside"] else 0.6,
                "summary": summ, "requests": []}

    def commit(self, obs: dict, message: dict, state: dict) -> dict:
        obs["recovery"]["consistency"] = obs["check"]
        return {"recovery": obs["recovery"]}

    def detail(self, obs: dict):
        return obs["recovery"]


def _consistency(recovery: dict) -> dict:
    pct, full = recovery["cohort_full_recovery_percentiles"], recovery["predicted_full_days"]
    if not pct:
        return {"inside": True, "note": "no cohort to compare with"}
    inside = pct["p10"] <= full <= pct["p90"]
    return {"inside": inside, "note": (f"{full} d is inside the cohort's P10-P90 ({pct['p10']:.0f}-{pct['p90']:.0f} d)" if inside
                                       else f"{full} d is outside the cohort's P10-P90 ({pct['p10']:.0f}-{pct['p90']:.0f} d)")}


recovery_node = RecoveryAgent()
