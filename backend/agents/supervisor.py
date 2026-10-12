"""
Supervisor Agent.
Agent-based orchestration: after every step control returns here, and the supervisor reads the
shared state and decides which agent runs next (or that the analysis is finished). Decisions are
rules over the evidence gathered so far (no LLM), each with a stated reason that is streamed to the
console and saved with the report.

What the supervisor can decide beyond the normal order:
  * investigate: run case retrieval and the Synapt worker in parallel when neither has run
  * broaden:     re-run retrieval with a wider query when the evidence is thin or not similar enough
  * re-ask:      call the Synapt worker again when graph-RAG returned no answer
  * rewrite:     send the briefing back to the Report agent (strict mode) when the fact-check flags figures
  * revise:      one revision round (broader evidence -> new plan -> new briefing) when the judge says "revise"
"""

from __future__ import annotations

from typing import Any

import numpy as np

from agents.state import emit

MAX_ROUTES = 25          # hard stop for the routing loop
MIN_CASES = 3            # fewer precedents than this is thin evidence
MIN_SIMILARITY = 0.6     # average attribute similarity below this is weak evidence
MAX_RETRIEVAL_ROUNDS = 2
MAX_GRAPH_ROUNDS = 2
MAX_REPORT_ROUNDS = 2
MAX_REVISIONS = 1

FINISH = "__end__"


def _avg_similarity(cases: list[dict]) -> float | None:
    sims = [c["similarity"] for c in cases if c.get("similarity") is not None]
    return float(np.mean(sims)) if sims else None


def decide(state: dict) -> tuple[list[str], str, dict[str, Any]]:
    """Pure routing policy: (next agents, reason, state updates). An empty agent list means finish."""
    payload = state.get("payload") or {}
    if state.get("routes", 0) >= MAX_ROUTES:
        return [], f"Stopping: routing limit of {MAX_ROUTES} decisions reached", {}

    if state.get("incident") is None:
        return ["classifier"], "No structured incident yet: the Intake agent classifies the description", {}

    need_search = state.get("search") is None
    need_synapt = state.get("synapt_round", 0) == 0
    if need_search and need_synapt:
        return (["hybrid_retriever", "synapt_worker"],
                "No evidence yet: retrieve similar cases and query Synapt (graph-RAG + playbook) in parallel", {})
    if need_search:
        return ["hybrid_retriever"], "Case retrieval needed for the current evidence round", {}
    if need_synapt:
        return ["synapt_worker"], "Synapt graph-RAG and playbook not fetched yet", {}

    cases = state.get("cases")
    if cases is None:
        return ["evidence_fusion"], "Merge retrieved cases with the Synapt graph-RAG cases", {}

    sim = _avg_similarity(cases)
    weak = len(cases) < MIN_CASES or (sim is not None and sim < MIN_SIMILARITY)
    if weak and state.get("retrieval_round", 0) < MAX_RETRIEVAL_ROUNDS:
        why = (f"only {len(cases)} similar case(s)" if len(cases) < MIN_CASES
               else f"average similarity {sim:.0%} is below {MIN_SIMILARITY:.0%}")
        return (["hybrid_retriever"], f"Evidence is weak ({why}): broaden the search and retrieve again",
                {"search": None, "cases": None, "retrieval_plan": {"broaden": True}})

    graph = state.get("graph")
    if (payload.get("use_graph", True) and not (graph or {}).get("answer")
            and state.get("synapt_round", 0) < MAX_GRAPH_ROUNDS):
        return (["synapt_worker"], "Synapt graph-RAG returned no answer: ask again with a broader question",
                {"cases": None})

    if state.get("impact") is None:
        if weak:
            return (["impact_analyzer"], f"Evidence still weak after {state.get('retrieval_round', 0)} retrieval "
                    "round(s): continue with the best cases found and predict impact, loss and recovery", {})
        return ["impact_analyzer"], "Evidence is sufficient: predict impact, loss and recovery", {}
    if state.get("plan") is None:
        return ["planner"], "Impact known: rank strategies and build the response plan", {}
    if state.get("recovery") is None:
        return ["recovery"], "Plan ready: project the recovery timeline", {}
    if state.get("summary") is None:
        return ["synthesis"], "All analysis in place: write the fact-checked briefing", {}

    fc = state.get("fact_check") or {}
    if not fc.get("passed", True) and state.get("report_round", 0) < MAX_REPORT_ROUNDS:
        return (["synthesis"],
                f"Fact-check flagged {len(fc.get('final') or [])} figure(s): rewrite the briefing in strict mode",
                {"summary": None})

    if payload.get("judge", True):
        verdict = state.get("verdict")
        if verdict is None:
            return ["judge"], "Briefing ready: audit it with the Judge agent", {}
        if verdict.get("verdict") == "revise" and state.get("revision", 0) < MAX_REVISIONS:
            return (["hybrid_retriever"],
                    f"Judge asked for a revision (score {verdict.get('overall_score', 0):.0%}): "
                    "broaden the evidence, then re-plan and re-write",
                    {"search": None, "cases": None, "plan": None, "recovery": None, "summary": None,
                     "verdict": None, "retrieval_plan": {"broaden": True},
                     "revision": state.get("revision", 0) + 1})
        return [], f"Judge verdict {verdict.get('verdict', '?').upper()}: analysis complete", {}

    return [], "Briefing ready and judge audit not requested: analysis complete", {}


def supervisor_node(state: dict) -> dict:
    """LangGraph node (Supervisor agent): decide the next agent(s) and record why."""
    nxt, reason, updates = decide(state)
    n = state.get("routes", 0) + 1
    decision = {"step": n, "next": nxt or ["finish"], "reason": reason}
    emit("route", "supervisor", **decision)
    return {**updates, "next_agents": nxt, "routes": n, "decisions": [decision]}


def route(state: dict) -> list[str] | str:
    """Conditional edge out of the supervisor: the agent(s) it chose, or END."""
    return state.get("next_agents") or FINISH
