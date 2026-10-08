"""
Impact Assessment & Prioritisation Agent.
Scores a disruption P1-P4 from severity, production impact, financial loss and the ML
high-impact risk, and maps it to an action SLA.
"""

from __future__ import annotations

import math

LOSS_CAP = 50_000_000


def priority(inc: dict, pred: dict | None = None) -> dict:
    """Weighted priority from severity, production impact and financial loss."""
    pred = pred or {}
    sev = int(inc.get("disruption_severity") or 3)
    impact = inc.get("production_impact_pct")
    impact = float(impact if impact is not None else pred.get("production_impact_pct", 30))
    loss = inc.get("revenue_loss_usd")
    loss = float(loss if loss is not None else pred.get("revenue_loss_usd", 1e6))
    s_sev = (sev - 1) / 4
    s_imp = min(impact, 100) / 100
    s_loss = min(1.0, math.log10(max(loss, 1e4) / 1e4) / math.log10(LOSS_CAP / 1e4))
    risk = pred.get("risk_probability")
    score = 0.35 * s_sev + 0.30 * s_imp + 0.25 * s_loss + 0.10 * (risk if risk is not None else s_sev)
    score = round(score * 100, 1)
    level = "P1 - Critical" if score >= 70 else "P2 - High" if score >= 50 else "P3 - Medium" if score >= 30 else "P4 - Low"
    sla = {"P1": "Mobilise war-room within 4h", "P2": "Response plan within 24h",
           "P3": "Review within 3 days", "P4": "Monitor weekly"}[level[:2]]
    return {"score": score, "level": level, "action_sla": sla,
            "components": {"severity": round(s_sev * 100, 1), "production_impact": round(s_imp * 100, 1),
                           "financial_loss": round(s_loss * 100, 1),
                           "risk": round((risk if risk is not None else s_sev) * 100, 1)},
            "inputs": {"severity": sev, "production_impact_pct": impact, "revenue_loss_usd": loss,
                       "estimated": {"impact": inc.get("production_impact_pct") is None,
                                     "loss": inc.get("revenue_loss_usd") is None}}}


def impact_analysis_node(state: dict) -> dict:
    """LangGraph node (Impact agent): ML predictions with P10-P90 ranges, explanations and P1-P4 priority."""
    import time

    from agents.prediction import registry
    from agents.state import done, emit

    t0 = time.time()
    emit("agent_start", "impact")
    incident = state["incident"]
    pred = registry.predict(incident)
    expl = registry.explain(incident)
    prio = priority(incident, pred)
    impact = {"prediction": pred, "priority": prio, "explanation": expl,
              "top_factors": {t: e["local"][:5] for t, e in expl.items()}}
    summ = (f"{prio['level']} (score {prio['score']}); impact ≈{pred['production_impact_pct']}%, loss ≈"
            f"${pred['revenue_loss_usd']:,.0f}, full recovery ≈{pred['full_recovery_days']:.0f}d, risk {pred['risk_level']}")
    return {"impact": impact, "trace": [done("impact", t0, summ, impact)]}
