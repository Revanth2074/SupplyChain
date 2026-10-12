"""
Response Planning Agent.
Ranks response strategies by historical effectiveness for comparable disruptions, blended
with ML counterfactual predictions and operator feedback boosts, then builds the action plan from
those statistics and the Synapt response playbook (trident_get_procedures). No LLM at runtime.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from agents.prediction import registry
from services import feedback
from services.data_store import store

def strategy_table(inc: dict) -> dict:
    """Historical effectiveness of each response strategy for comparable disruptions +
    ML counterfactual predictions for this incident under each strategy."""
    df = store.df
    scope = {"disruption_type": inc.get("disruption_type")}
    sub = df[df["disruption_type"] == inc["disruption_type"]] if inc.get("disruption_type") else df
    scope_desc = [f"type={inc.get('disruption_type')}"] if inc.get("disruption_type") else ["all"]
    if inc.get("industry"):
        s2 = sub[sub["industry"] == inc["industry"]]
        if len(s2) >= 300:
            sub, scope["industry"] = s2, inc["industry"]
            scope_desc.append(f"industry={inc['industry']}")
    if inc.get("has_backup_supplier") is not None:
        s3 = sub[sub["has_backup_supplier"] == bool(inc["has_backup_supplier"])]
        if len(s3) >= 200:
            sub = s3
            scope_desc.append(f"backup={bool(inc['has_backup_supplier'])}")
    if inc.get("disruption_severity"):
        sv = int(inc["disruption_severity"])
        s4 = sub[sub["disruption_severity"].between(sv - 1, sv + 1)]
        if len(s4) >= 150:
            sub = s4
            scope_desc.append(f"severity={sv}±1")

    g = sub.groupby("response_type").agg(
        cases=("disruption_id", "count"), avg_full_recovery=("full_recovery_days", "mean"),
        median_full_recovery=("full_recovery_days", "median"), avg_partial_recovery=("partial_recovery_days", "mean"),
        avg_revenue_loss=("revenue_loss_usd", "mean"), avg_impact=("production_impact_pct", "mean"),
        supplier_change_rate=("permanent_supplier_change", "mean"), avg_response_time=("response_time_days", "mean"),
    ).reset_index()
    boosts = feedback.strategy_boosts()
    rows = []
    for _, r in g.iterrows():
        cf_inc = {**inc, "response_type": r["response_type"]}
        p = registry.predict(cf_inc) if registry.ready else {}
        rows.append({
            "strategy": r["response_type"], "cases": int(r["cases"]),
            "avg_full_recovery": round(r["avg_full_recovery"], 1), "median_full_recovery": float(r["median_full_recovery"]),
            "avg_partial_recovery": round(r["avg_partial_recovery"], 1), "avg_revenue_loss": round(r["avg_revenue_loss"], 0),
            "avg_impact": round(r["avg_impact"], 1), "supplier_change_rate": round(r["supplier_change_rate"], 3),
            "pred_full_recovery": p.get("full_recovery_days"), "pred_partial_recovery": p.get("partial_recovery_days"),
            "pred_revenue_loss": p.get("revenue_loss_usd"),
            "feedback_boost": boosts.get((inc.get("disruption_type"), r["response_type"]), 1.0),
        })
    if not rows:
        return {"scope": scope_desc, "n": 0, "strategies": []}
    t = pd.DataFrame(rows)

    def inv_norm(s):
        s = s.astype(float)
        return 1 - (s - s.min()) / (s.max() - s.min()) if s.max() > s.min() else pd.Series(1.0, index=s.index)

    rec = t["pred_full_recovery"].fillna(t["avg_full_recovery"])
    loss = t["pred_revenue_loss"].fillna(t["avg_revenue_loss"])
    conf = np.clip(np.log10(t["cases"] + 1) / 3.5, 0.3, 1.0)
    t["effectiveness"] = ((0.35 * inv_norm(t["avg_full_recovery"]) + 0.25 * inv_norm(rec) +
                           0.25 * inv_norm(loss) + 0.15 * inv_norm(t["avg_partial_recovery"])) * conf *
                          t["feedback_boost"] * 100).round(1)
    t = t.sort_values("effectiveness", ascending=False)
    return {"scope": scope_desc, "n": int(len(sub)), "strategies": t.replace({np.nan: None}).to_dict("records")}


EVIDENCE_FIELDS = ("disruption_id", "disruption_type", "industry", "supplier_tier", "has_backup_supplier",
                   "disruption_severity", "production_impact_pct", "revenue_loss_usd", "response_type",
                   "response_time_days", "partial_recovery_days", "full_recovery_days", "similarity")


def statistics_plan(inc: dict, strategies: list[dict], cases: list[dict]) -> dict:
    """Plan from strategy statistics: best-ranked strategy first, cited comparable cases."""
    top = strategies[0]["strategy"] if strategies else "Alternative Supplier"
    sec = strategies[1]["strategy"] if len(strategies) > 1 else "Inventory Buffer"
    cited = [c["disruption_id"] for c in cases if c.get("response_type") == top][:3]
    acts = {
        "Alternative Supplier": "Activate qualified alternative suppliers and issue expedited POs",
        "Inventory Buffer": "Release safety stock and re-allocate inventory to critical SKUs",
        "Production Reroute": "Reroute production to alternate plants/lines with available capacity",
        "Customer Delay": "Notify key customers, renegotiate delivery schedules and prioritise orders",
        "Combined Strategy": "Run combined playbook: alt sourcing + buffer release + selective rerouting",
    }
    return {
        "primary_strategy": top, "secondary_strategy": sec,
        "rationale": _rationale(inc, strategies),
        "immediate_actions": [
            {"action": "Stand up disruption response team and confirm scope of affected parts", "owner": "Supply Chain Ops Lead", "timeframe": "0-24h"},
            {"action": acts.get(top, f"Execute {top}"), "owner": "Procurement", "timeframe": "24-72h"},
            {"action": "Quantify exposure: open orders, inventory cover days, revenue at risk", "owner": "Planning / Finance", "timeframe": "0-48h"},
        ],
        "short_term_actions": [acts.get(sec, f"Prepare {sec} as fallback"), "Daily recovery stand-up with KPI tracking"],
        "long_term_actions": ["Qualify a backup supplier for affected parts" if not inc.get("has_backup_supplier") else
                              "Review backup supplier capacity contracts", "Update risk register and BCP playbooks"],
        "risks": _risks(inc, strategies),
        "cited_cases": cited, "method": "statistics",
    }


def _rationale(inc: dict, strategies: list[dict]) -> str:
    if not strategies:
        return "No comparable cases; default strategy."
    t = strategies[0]
    txt = (f"{t['strategy']} has the highest effectiveness score ({t['effectiveness']}) for comparable "
           f"{inc.get('disruption_type')} cases; the score blends average and predicted full recovery, revenue loss "
           f"and partial recovery, weighted by sample size. It averaged {t['avg_full_recovery']} days to full "
           f"recovery across {t['cases']} cases.")
    if len(strategies) > 1:
        s2 = strategies[1]
        txt += f" {s2['strategy']} is next ({s2['avg_full_recovery']} days, {s2['cases']} cases)."
    fastest = min(strategies, key=lambda s: s["avg_full_recovery"])
    if fastest["strategy"] != t["strategy"]:
        txt += (f" {fastest['strategy']} recovered fastest on average ({fastest['avg_full_recovery']} days) but "
                f"ranks lower overall (effectiveness {fastest['effectiveness']}, {fastest['cases']} cases).")
    return txt


def _risks(inc: dict, strategies: list[dict]) -> list[str]:
    risks = ["Prolonged recovery if the primary strategy capacity is insufficient"]
    if strategies and (strategies[0].get("supplier_change_rate") or 0) >= 0.25:
        risks.append(f"{strategies[0]['supplier_change_rate']:.0%} of comparable cases ended in a permanent "
                     "supplier change")
    if inc.get("has_backup_supplier") is False:
        risks.append("No qualified backup supplier: single-source exposure")
    if (inc.get("disruption_severity") or 0) >= 4:
        risks.append("High severity: escalate early per the playbook escalation chain")
    return risks


def apply_playbook(plan: dict, procedure: dict | None) -> dict:
    """Put the Synapt playbook steps (ordered SOP from the Procedure Store) into the plan."""
    if not procedure or not procedure.get("steps"):
        return plan
    steps = procedure["steps"]
    plan["immediate_actions"] = [{"action": st["text"], "owner": "Per Synapt playbook", "timeframe": f"Step {st['n']}"}
                                 for st in steps[:3]] + plan["immediate_actions"][1:2]
    plan["short_term_actions"] = [st["text"] for st in steps[3:]] + plan["short_term_actions"]
    plan["rationale"] += f" Steps follow the Synapt playbook \"{procedure['name']}\"."
    plan["method"] = "statistics+synapt-playbook"
    return plan


def planner_node(state: dict) -> dict:
    """LangGraph node (Planning agent): rank strategies, then build the plan from the statistics and the
    Synapt playbook."""
    import time

    from agents.state import done, emit

    t0 = time.time()
    emit("agent_start", "planner")
    incident, cases = state["incident"], state["cases"]
    procedure = state.get("procedure")
    strat = strategy_table(incident)
    evidence_cases = [{k: c.get(k) for k in EVIDENCE_FIELDS} for c in cases[:10]]
    plan = apply_playbook(statistics_plan(incident, strat["strategies"], cases), procedure)
    plan["procedure"] = procedure
    summ = f"Primary: {plan.get('primary_strategy')} · Secondary: {plan.get('secondary_strategy')} ({plan.get('method')})"
    if procedure:
        summ += f" · Synapt playbook: {len(procedure['steps'])} steps"
    entry = done("planner", t0, summ, {"strategies": strat, "plan": plan})
    return {"strategies": strat, "plan": plan, "evidence_cases": evidence_cases, "trace": [entry]}
