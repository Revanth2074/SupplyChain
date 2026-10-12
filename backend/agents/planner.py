"""
Response Planning Agent.
Ranks response strategies by historical effectiveness for comparable disruptions, blended
with precedent counterfactuals (the same profile handled with each strategy) and operator feedback boosts, then builds the action plan from
those statistics and the Synapt response playbook (trident_get_procedures). No LLM at runtime.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from agents.base import Action, Agent, Tool
from agents.precedent import estimator
from services import feedback
from services.data_store import store

def strategy_table(inc: dict) -> dict:
    """Historical effectiveness of each response strategy for comparable disruptions +
    precedent estimates for this incident under each strategy (cohort statistics, strategy held fixed)."""
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
        p = estimator.predict(cf_inc, keep=("response_type",), pair=inc) if estimator.ready else {}
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


MIN_SUPPORT = 30  # a primary strategy needs at least this many comparable cases behind it


class PlannerAgent(Agent):
    """Goal: an executable plan whose primary strategy is well supported by comparable cases and follows
    the Synapt playbook. Tools: the strategy-effectiveness table (history x ML counterfactuals x feedback),
    the Synapt playbook (trident_get_procedures, fetched itself if the investigation did not bring one),
    and the plan builder. The agent rejects a top-ranked strategy with too few comparable cases (or one the
    Judge asked it to reconsider) and re-drafts with the next one."""

    id, node = "planner", "planner"
    goal = f"A plan whose primary strategy has at least {MIN_SUPPORT} comparable cases, with playbook steps"
    max_steps = 5

    def make_tools(self) -> list[Tool]:
        return [Tool("rank_strategies", "Effectiveness of each response strategy for comparable disruptions",
                     lambda incident: strategy_table(incident)),
                Tool("fetch_playbook", "trident_get_procedures for this disruption type", lambda disruption_type: _playbook(disruption_type), soft=True),
                Tool("draft_plan", "Build the plan from the ranked strategies and cited cases",
                     lambda incident, strategies, cases: statistics_plan(incident, strategies, cases))]

    def perceive(self, state: dict) -> dict:
        return {"incident": state["incident"], "cases": state["cases"], "procedure": state.get("procedure"),
                "fetched": False, "table": None, "ranked": None, "plan": None, "rejected": [],
                "exclude": set((state.get("plan_hint") or {}).get("exclude") or [])}

    def _candidates(self, obs: dict) -> list[dict]:
        return [s for s in obs["table"]["strategies"] if s["strategy"] not in obs["rejected"]]

    def decide(self, obs: dict, steps: list[dict]) -> Action | None:
        if obs["table"] is None:
            return Action("rank_strategies", {"incident": obs["incident"]}, "Rank the response strategies for comparable disruptions")
        if obs["procedure"] is None and not obs["fetched"]:
            from agents import synapt_tools as syn
            if syn.configured():
                return Action("fetch_playbook", {"disruption_type": obs["incident"]["disruption_type"]},
                              "No playbook in the evidence yet: fetch it from Synapt's Procedure Store")
        cands = self._candidates(obs)
        if obs["plan"] is None or (obs["plan"]["primary_strategy"] in obs["rejected"] and cands):
            top = cands[0] if cands else None
            thought = ("Draft the plan from the best-ranked strategy" if not obs["rejected"]
                       else f"Re-draft without {', '.join(obs['rejected'])}")
            if top:
                thought += f" ({top['strategy']}, {top['cases']} cases)"
            return Action("draft_plan", {"incident": obs["incident"], "strategies": cands or obs["table"]["strategies"],
                                         "cases": obs["cases"]}, thought)
        return None

    def observe(self, obs: dict, action: Action, result, error: str | None) -> dict:
        if action.tool == "rank_strategies":
            obs["table"] = result
            for s in result["strategies"]:
                low = s["cases"] < MIN_SUPPORT
                if (s["strategy"] in obs["exclude"] or low) and len(self._candidates(obs)) > 2:
                    obs["rejected"].append(s["strategy"])
        elif action.tool == "fetch_playbook":
            obs["fetched"] = True
            obs["procedure"] = result or obs["procedure"]
        else:
            obs["plan"] = apply_playbook(result, obs["procedure"])
        return obs

    def summarise(self, action: Action, result, error: str | None) -> str:
        if error:
            return f"failed ({error})"
        if action.tool == "rank_strategies":
            top = result["strategies"][:3]
            return "top: " + ", ".join(f"{s['strategy']} {s['effectiveness']} ({s['cases']} cases)" for s in top)
        if action.tool == "fetch_playbook":
            return f"{result['name']} ({len(result['steps'])} steps)" if result else "no playbook found"
        return f"primary {result['primary_strategy']}, secondary {result['secondary_strategy']}"

    def reflect(self, obs: dict, steps: list[dict]) -> dict:
        plan = obs["plan"]
        top = next((s for s in obs["table"]["strategies"] if s["strategy"] == plan["primary_strategy"]), {})
        support = top.get("cases", 0)
        conf = min(1.0, 0.5 + 0.5 * min(1.0, support / 200)) - (0 if obs["procedure"] else 0.1)
        summ = f"Primary: {plan.get('primary_strategy')} · Secondary: {plan.get('secondary_strategy')} ({plan.get('method')})"
        if obs["procedure"]:
            summ += f" · Synapt playbook: {len(obs['procedure']['steps'])} steps"
        if obs["rejected"]:
            summ += f" · rejected {', '.join(obs['rejected'])}"
        return {"status": "done" if support >= MIN_SUPPORT else "partial", "confidence": round(conf, 2),
                "summary": summ, "requests": []}

    def commit(self, obs: dict, message: dict, state: dict) -> dict:
        plan = obs["plan"]
        plan["procedure"] = obs["procedure"]
        plan["rejected_strategies"] = obs["rejected"]
        obs["out"] = {"strategies": obs["table"], "plan": plan}
        return {"strategies": obs["table"], "plan": plan, "procedure": obs["procedure"], "plan_hint": {},
                "evidence_cases": [{k: c.get(k) for k in EVIDENCE_FIELDS} for c in obs["cases"][:10]]}

    def detail(self, obs: dict):
        return obs.get("out")


def _playbook(disruption_type: str):
    from agents import synapt_tools as syn
    return syn.procedure_for(disruption_type)


planner_node = PlannerAgent()
