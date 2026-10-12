"""
Impact Assessment & Prioritisation Agent.
Estimates impact, loss and recovery from comparable past disruptions (Synapt precedents + cohort
statistics, no trained model), scores the disruption P1-P4 and maps it to an action SLA.
"""

from __future__ import annotations

import math

from agents.base import Action, Agent, Tool

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


DISAGREE = 0.5      # Synapt precedents vs cohort gap (relative) that the agent flags
MIN_PRECEDENTS = 5  # fewer close Synapt precedents than this is thin evidence


class ImpactAgent(Agent):
    """Goal: an impact estimate the team can rely on, with an honest confidence. No trained model.
    Tools: Synapt precedents (trident_get_chunks: the nearest past cases and what happened to them),
    the precedent estimate (median and P10-P90 of the closest cohort of past cases, plus the drivers),
    and the P1-P4 priority formula. When the Synapt precedents and the cohort disagree strongly, or
    Synapt finds few close cases, the agent lowers its confidence and says so in its report."""

    id, node = "impact", "impact_analyzer"
    goal = "Estimate impact, loss and recovery from comparable past cases, cross-check them and set the priority"
    max_steps = 3

    def make_tools(self) -> list[Tool]:
        from agents.precedent import estimator
        return [Tool("synapt_precedents", "Nearest past cases from Synapt (trident_get_chunks) and their outcomes",
                     lambda incident: estimator.synapt_precedents(incident)),
                Tool("precedent_estimate", "Median and P10-P90 of the closest cohort of past cases, with drivers",
                     lambda incident: {"prediction": estimator.predict(incident), "explanation": estimator.explain(incident)}),
                Tool("priority", "P1-P4 from severity, impact, log-loss and risk", lambda incident, prediction: priority(incident, prediction))]

    def perceive(self, state: dict) -> dict:
        return {"incident": state["incident"], "synapt": None, "pred": None, "expl": None, "prio": None, "flags": []}

    def decide(self, obs: dict, steps: list[dict]) -> Action | None:
        if obs["synapt"] is None:
            return Action("synapt_precedents", {"incident": obs["incident"]},
                          "Ask Synapt for the past cases closest to this incident")
        if obs["pred"] is None:
            n = obs["synapt"].get("used", 0)
            return Action("precedent_estimate", {"incident": obs["incident"]},
                          f"{n} close Synapt precedent(s): estimate from the full cohort of comparable cases and cross-check")
        if obs["prio"] is None:
            return Action("priority", {"incident": obs["incident"], "prediction": obs["pred"]}, "Score the priority and SLA")
        return None

    def observe(self, obs: dict, action: Action, result, error: str | None) -> dict:
        if action.tool == "synapt_precedents":
            obs["synapt"] = result
            if result.get("used", 0) < MIN_PRECEDENTS:
                obs["flags"].append(f"only {result.get('used', 0)} close Synapt precedent(s)")
        elif action.tool == "precedent_estimate":
            obs["pred"], obs["expl"] = result["prediction"], result["explanation"]
            obs["pred"]["synapt_precedents"] = obs["synapt"]
            s, p = obs["synapt"], obs["pred"]
            if s.get("full_recovery_days"):
                gap = abs(p["full_recovery_days"] - s["full_recovery_days"]) / max(s["full_recovery_days"], 1)
                if gap > DISAGREE:
                    obs["flags"].append(f"cohort full recovery {p['full_recovery_days']:.0f} d vs Synapt precedents "
                                        f"{s['full_recovery_days']:.0f} d ({gap:.0%} apart)")
        else:
            obs["prio"] = result
        return obs

    def summarise(self, action: Action, result, error: str | None) -> str:
        if action.tool == "synapt_precedents":
            if not result.get("used"):
                return "Synapt returned no comparable cases"
            return (f"{result['used']} close precedent(s) (avg similarity {result['avg_similarity']:.2f}): "
                    f"median full recovery {result.get('full_recovery_days', 0):.0f} d")
        if action.tool == "precedent_estimate":
            p = result["prediction"]
            return (f"cohort of {p['cohort']['cases']} cases: impact {p['production_impact_pct']}%, loss "
                    f"${p['revenue_loss_usd']:,.0f}, full recovery {p['full_recovery_days']:.0f} d, "
                    f"support {(p.get('support') or {}).get('level', '?')}")
        return f"{result['level']} (score {result['score']})"

    def reflect(self, obs: dict, steps: list[dict]) -> dict:
        pred, prio = obs["pred"], obs["prio"]
        level = (pred.get("support") or {}).get("level")
        conf = {"high": 0.9, "medium": 0.75, "low": 0.55}.get(level, 0.7) - (0.15 if obs["flags"] else 0)
        summ = (f"{prio['level']} (score {prio['score']}); impact ≈{pred['production_impact_pct']}%, loss ≈"
                f"${pred['revenue_loss_usd']:,.0f}, full recovery ≈{pred['full_recovery_days']:.0f}d, risk {pred['risk_level']}"
                + (" · " + "; ".join(obs["flags"]) if obs["flags"] else " · Synapt precedents agree"))
        return {"status": "partial" if obs["flags"] else "done", "confidence": round(conf, 2), "summary": summ, "requests": []}

    def commit(self, obs: dict, message: dict, state: dict) -> dict:
        impact = {"prediction": obs["pred"], "priority": obs["prio"], "explanation": obs["expl"],
                  "top_factors": {t: e["local"][:5] for t, e in obs["expl"].items()},
                  "precedent": obs["synapt"], "checks": obs["flags"], "confidence": message["confidence"]}
        obs["impact"] = impact
        return {"impact": impact}

    def detail(self, obs: dict):
        return obs.get("impact")


impact_analysis_node = ImpactAgent()
