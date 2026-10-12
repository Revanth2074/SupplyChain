"""Judge agent.
At runtime the workflow uses `audit`: a deterministic rubric over the report, the evidence and the
fact-check (no LLM). The external LLM (aicredits.in) is used only as the independent judge in
`judge` — called by the evaluation suite, scripts/llm_judge.py and POST /api/judge."""
from __future__ import annotations

import json
import logging
import re

from agents.base import Action, Agent, Tool
from services import llm
from config import settings

log = logging.getLogger("judge")

CRITERIA = {
    "groundedness": "Claims, numbers and case IDs are supported by the provided evidence (similar cases, statistics, predictions). No fabricated facts.",
    "relevance": "Analysis addresses the specific incident (type, industry, tier, severity, backup status).",
    "actionability": "Recommendations are concrete, prioritised, time-bound and executable by an operations team.",
    "completeness": "Covers investigation, impact, response plan and recovery outlook including risks.",
    "consistency": "Recommendations are consistent with the strategy effectiveness data and the precedent estimates.",
    "safety": "No harmful, unethical, or overconfident claims; uncertainty acknowledged where appropriate.",
}

JUDGE_SYS = f"""You are an impartial senior supply-chain risk auditor acting as an LLM judge.
Score the ASSISTANT REPORT against the EVIDENCE using this rubric (1=poor, 5=excellent):
{json.dumps(CRITERIA, indent=1)}
Return JSON: {{"scores":{{criterion:int}}, "issues":[str], "strengths":[str],
"verdict":"approve"|"revise"|"reject", "summary":"2 sentences"}}"""


def audit(report_text: str, evidence: dict, fact_check: dict | None = None) -> dict:
    """Deterministic rubric audit (runtime judge)."""
    ids = set(re.findall(r"DIS-\d{6}", report_text))
    ev_ids = {c.get("disruption_id") for c in evidence.get("cases", [])}
    cited_ok = len(ids & ev_ids)
    fabricated = len(ids - ev_ids)
    has_num = bool(re.search(r"\d+\s*(days|%)", report_text))
    s = {
        "groundedness": max(1, min(5, 3 + min(cited_ok, 2) - min(fabricated, 2))),
        "relevance": 4 if evidence.get("incident", {}).get("disruption_type", "~~") in report_text else 3,
        "actionability": 4 if re.search(r"(?i)(day|hour|week|immediately|within)", report_text) else 2,
        "completeness": 4 if all(w in report_text.lower() for w in ("impact", "recover")) else 3,
        "consistency": 4 if evidence.get("top_strategy", "~~") in report_text else 3,
        "safety": 5,
    }
    if not has_num:
        s["groundedness"] = min(s["groundedness"], 3)
    if fact_check is not None:
        s["groundedness"] = 5 if fact_check.get("passed") else min(s["groundedness"], 2)
    if evidence.get("procedure"):
        s["actionability"] = 5
    return {"scores": s, "issues": ([f"{fabricated} case IDs not found in evidence"] if fabricated else []),
            "strengths": [f"Cites {cited_ok} retrieved cases"] if cited_ok else [],
            "verdict": "approve" if sum(s.values()) / 6 >= 3.5 else "revise",
            "summary": "Rule audit: case IDs, figures (fact-check), incident fields, strategy and playbook.",
            "method": "rules"}


def judge(report_text: str, evidence: dict) -> dict:
    ev = {
        "incident": evidence.get("incident"),
        "similar_cases": [{k: c.get(k) for k in ("disruption_id", "disruption_type", "industry", "disruption_severity",
                                                   "production_impact_pct", "revenue_loss_usd", "response_type",
                                                   "full_recovery_days")} for c in evidence.get("cases", [])[:8]],
        "strategy_stats": evidence.get("strategies", [])[:5],
        "predictions": evidence.get("prediction"),
    }
    try:
        if not llm.available():
            raise RuntimeError("LLM unavailable")
        j = llm.chat_json(JUDGE_SYS, f"EVIDENCE:\n{json.dumps(ev, default=str)}\n\nASSISTANT REPORT:\n{report_text}",
                          model=settings.JUDGE_MODEL, temperature=0)
        scores = {k: int(max(1, min(5, int((j.get("scores") or {}).get(k, 3))))) for k in CRITERIA}
        res = {"scores": scores, "issues": j.get("issues", [])[:6], "strengths": j.get("strengths", [])[:6],
               "verdict": j.get("verdict", "revise"), "summary": j.get("summary", ""), "method": "llm",
               "model": settings.JUDGE_MODEL}
    except Exception as e:  # noqa: BLE001
        log.warning("Judge fallback: %s", e)
        res = audit(report_text, {**evidence, "cases": evidence.get("cases", [])})
    res["overall_score"] = round(sum(res["scores"].values()) / (5 * len(res["scores"])), 3)
    res["criteria"] = CRITERIA
    return res


# What to redo when the Judge says "revise": the weakest criterion decides which agent gets the work back.
REMEDY = {
    "groundedness": ("synthesis", ["summary", "verdict"], {"report_mode": "strict"},
                     "figures or case IDs are not well supported: rewrite the briefing in strict mode"),
    "relevance": ("hybrid_retriever", ["search", "cases", "plan", "recovery", "summary", "verdict"], {"retrieval_plan": {"focus": True}},
                  "the analysis is not specific to this incident: re-investigate focused on its exact disruption type"),
    "actionability": ("planner", ["plan", "recovery", "summary", "verdict"], {},
                      "the plan is not concrete enough: re-plan with the Synapt playbook"),
    "completeness": ("recovery", ["recovery", "summary", "verdict"], {},
                     "the outlook is incomplete: re-project recovery and rewrite"),
    "consistency": ("planner", ["plan", "recovery", "summary", "verdict"], {"plan_hint": "exclude_primary"},
                    "the recommendation does not match the strategy statistics: re-plan without the current primary"),
    "safety": ("synthesis", ["summary", "verdict"], {"report_mode": "strict"},
               "the briefing overstates certainty: rewrite it in strict mode"),
}


class JudgeAgent(Agent):
    """Goal: a verdict on the analysis against six criteria, and - when it is not good enough - a precise
    request to the agent whose work caused the weakest score. Tool: the deterministic rubric audit (no LLM;
    the external LLM judge is used only in evaluation)."""

    id, node = "judge", "judge"
    goal = "Audit the analysis on six criteria and send weak work back to the agent responsible"
    max_steps = 1

    def make_tools(self) -> list[Tool]:
        return [Tool("rubric_audit", "Six-criterion rubric over the briefing, plan, evidence and fact-check",
                     lambda report_text, evidence, fact_check: audit(report_text, evidence, fact_check))]

    def perceive(self, state: dict) -> dict:
        plan = state["plan"]
        return {"enabled": state["payload"].get("judge", True), "plan": plan,
                "report_text": state["summary"] + "\n\nPLAN:\n" + json.dumps(plan, default=str),
                "evidence": {"incident": state["incident"], "cases": state["cases"], "top_strategy": plan.get("primary_strategy"),
                             "procedure": plan.get("procedure")},
                "fact_check": state.get("fact_check"), "verdict": None}

    def decide(self, obs: dict, steps: list[dict]) -> Action | None:
        if obs["enabled"] and obs["verdict"] is None:
            return Action("rubric_audit", {"report_text": obs["report_text"], "evidence": obs["evidence"], "fact_check": obs["fact_check"]},
                          "Score groundedness, relevance, actionability, completeness, consistency and safety")
        return None

    def observe(self, obs: dict, action: Action, result, error: str | None) -> dict:
        result["overall_score"] = round(sum(result["scores"].values()) / (5 * len(result["scores"])), 3)
        result["criteria"] = CRITERIA
        obs["verdict"] = result
        return obs

    def summarise(self, action: Action, result, error: str | None) -> str:
        return ", ".join(f"{k} {v}" for k, v in result["scores"].items())

    def reflect(self, obs: dict, steps: list[dict]) -> dict:
        v = obs["verdict"]
        if v is None:
            return {"status": "done", "confidence": None, "summary": "skipped", "requests": []}
        requests = []
        if v["verdict"] == "revise":
            weakest = min(v["scores"], key=lambda k: (v["scores"][k], list(CRITERIA).index(k)))
            to, reset, params, why = REMEDY[weakest]
            if params.get("plan_hint") == "exclude_primary":
                params = {"plan_hint": {"exclude": [obs["plan"].get("primary_strategy")]}}
            requests.append({"to": to, "reset": reset, "params": params, "criterion": weakest,
                             "reason": f"{weakest} scored {v['scores'][weakest]}/5: {why}"})
            v["remedy"] = requests[0]
        return {"status": "done" if v["verdict"] == "approve" else "partial", "confidence": v["overall_score"],
                "summary": f"{v['verdict'].upper()} · score {v['overall_score']:.0%} ({v['method']})"
                           + (f" · asks {requests[0]['to'].replace('_', ' ')} to fix {requests[0]['criterion']}" if requests else ""),
                "requests": requests}

    def commit(self, obs: dict, message: dict, state: dict) -> dict:
        return {"verdict": obs["verdict"]}

    def detail(self, obs: dict):
        return obs["verdict"]


judge_node = JudgeAgent()
