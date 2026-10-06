"""LLM-as-Judge: validates disruption analysis & recommendations against the
retrieved evidence with a fixed rubric. Heuristic fallback when LLM is down."""
from __future__ import annotations

import json
import logging
import re

from . import llm
from .config import settings

log = logging.getLogger("judge")

CRITERIA = {
    "groundedness": "Claims, numbers and case IDs are supported by the provided evidence (similar cases, statistics, predictions). No fabricated facts.",
    "relevance": "Analysis addresses the specific incident (type, industry, tier, severity, backup status).",
    "actionability": "Recommendations are concrete, prioritised, time-bound and executable by an operations team.",
    "completeness": "Covers investigation, impact, response plan and recovery outlook including risks.",
    "consistency": "Recommendations are consistent with the strategy effectiveness data and ML predictions.",
    "safety": "No harmful, unethical, or overconfident claims; uncertainty acknowledged where appropriate.",
}

JUDGE_SYS = f"""You are an impartial senior supply-chain risk auditor acting as an LLM judge.
Score the ASSISTANT REPORT against the EVIDENCE using this rubric (1=poor, 5=excellent):
{json.dumps(CRITERIA, indent=1)}
Return JSON: {{"scores":{{criterion:int}}, "issues":[str], "strengths":[str],
"verdict":"approve"|"revise"|"reject", "summary":"2 sentences"}}"""


def _heuristic(report_text: str, evidence: dict) -> dict:
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
    return {"scores": s, "issues": ([f"{fabricated} case IDs not found in evidence"] if fabricated else []),
            "strengths": [f"Cites {cited_ok} retrieved cases"] if cited_ok else [],
            "verdict": "approve" if sum(s.values()) / 6 >= 3.5 else "revise",
            "summary": "Heuristic rubric evaluation (LLM judge unavailable).", "method": "heuristic"}


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
        res = _heuristic(report_text, {**evidence, "cases": evidence.get("cases", [])})
    res["overall_score"] = round(sum(res["scores"].values()) / (5 * len(res["scores"])), 3)
    res["criteria"] = CRITERIA
    return res
