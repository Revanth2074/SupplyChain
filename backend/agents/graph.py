"""
LangGraph Agent-Based Orchestration Graph (supervisor + goal-driven agents on a shared blackboard).

Guardrails run first. After that a Supervisor agent sits at the centre: it holds the analysis goals,
each owned by an agent, and after every step it schedules all agents whose goal is open and whose
inputs are ready (in parallel), acts on requests the agents post in their messages (e.g. the Judge
asking the Planner to re-plan), and decides when the analysis is finished.

Every worker is a goal-driven agent (agents/base.py): it perceives the shared state, chooses its own
tools step by step (perceive -> decide -> act -> observe), reflects on whether its goal is met, and
reports a message with its status, confidence, steps and any requests. No LLM is involved.

    START -> guardrails --(invalid)--> END
                 |
                 v
            supervisor <---------------------------------------------------+
                 |  goals x dependencies x requests -> next agent(s)        |
                 +--> classifier        Intake: rules, then Synapt labels   |
                 +--> hybrid_retriever  |                                   |
                 +--> synapt_worker     |  Investigation + Impact,           |  every agent
                 +--> impact_analyzer   |  started together                  |  reports back to
                 +--> evidence_fusion                                        |  the supervisor
                 +--> planner           rejects weak strategies, playbook   |
                 +--> recovery          checks against the cohort           |
                 +--> synthesis         drafts, fact-checks, rewrites        |
                 +--> judge             audits; asks an agent to redo       |
                 +--> END  (all goals met, or the routing limit)            |
                 ------------------------------------------------------------+

Streamed events (stream_mode="custom"): agent_start / agent_step / agent_done from the agents and
`route` from the supervisor; the console shows them live over Server-Sent Events.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Iterator, Literal

from fastapi import HTTPException
from langgraph.graph import END, START, StateGraph

from agents.classifier import classifier_node
from agents.guardrails import guardrails_node
from agents.impact_analysis import impact_analysis_node
from agents.judge import judge_node
from agents.planner import planner_node
from agents.recovery import recovery_node
from agents.retrieval import evidence_fusion_node, hybrid_retrieval_node
from agents.state import DisruptionAgentState
from agents.supervisor import route, supervisor_node
from agents.synapt_tools import synapt_worker_node
from agents.synthesis import synthesis_node
from services import feedback

WORKERS = {
    "classifier": classifier_node,
    "hybrid_retriever": hybrid_retrieval_node,
    "synapt_worker": synapt_worker_node,
    "evidence_fusion": evidence_fusion_node,
    "impact_analyzer": impact_analysis_node,
    "planner": planner_node,
    "recovery": recovery_node,
    "synthesis": synthesis_node,
    "judge": judge_node,
}
RECURSION_LIMIT = 80  # supersteps; the supervisor's own MAX_ROUTES stops the loop well before this


def guardrail_decision(state: DisruptionAgentState) -> Literal["supervisor", "__end__"]:
    """Conditional routing based on input guardrail checks."""
    guardrail = state.get("guardrail_result")
    if guardrail and not guardrail.get("is_valid", True):
        return END
    return "supervisor"


def build_disruption_agent_graph():
    """Builds and compiles the supervisor-centred StateGraph."""
    workflow = StateGraph(DisruptionAgentState)

    # 1. Guardrails, the supervisor and the worker agents
    workflow.add_node("guardrails", guardrails_node)
    workflow.add_node("supervisor", supervisor_node)
    for name, fn in WORKERS.items():
        workflow.add_node(name, fn)

    # 2. Entry: START -> guardrails -> supervisor OR END
    workflow.add_edge(START, "guardrails")
    workflow.add_conditional_edges("guardrails", guardrail_decision, {"supervisor": "supervisor", END: END})

    # 3. The supervisor picks the next agent(s); a list fans out in parallel
    workflow.add_conditional_edges("supervisor", route, [*WORKERS, END])

    # 4. Every agent reports back to the supervisor
    for name in WORKERS:
        workflow.add_edge(name, "supervisor")

    return workflow.compile()


# Compile Singleton Graph
disruption_agent_graph = build_disruption_agent_graph()


def _initial_state(payload: dict) -> DisruptionAgentState:
    return {"payload": payload, "started_at": time.time(), "trace": []}


def _raise_guardrail(g: dict) -> None:
    if g.get("kind") == "value":
        raise ValueError(g["message"])
    raise HTTPException(g.get("status", 422), g["message"])


def _report(state: DisruptionAgentState) -> Dict[str, Any]:
    """Assemble the final analysis, persist it, and return it (the SSE `result` event payload)."""
    graph, search, incident = state.get("graph"), state["search"], state["incident"]
    cases, verdict = state["cases"], state.get("verdict")
    report = {"incident": incident, "classification": state["classification"], "warnings": state.get("warnings", []),
              "query": state["query"], "cases": cases,
              "search_meta": {k: v for k, v in search.items() if k != "results"},
              "graph": graph, "impact": state["impact"], "strategies": state["strategies"], "plan": state["plan"],
              "recovery": state["recovery"], "summary": state["summary"], "facts": state["facts"],
              "fact_check": state["fact_check"], "judge": verdict, "trace": state["trace"],
              "decisions": state.get("decisions", []),
              "messages": state.get("messages", []),
              "total_ms": int((time.time() - state["started_at"]) * 1000),
              "retrieval_context": [c["text"] for c in cases[:8]] +
                                   ([graph["answer"]] if graph and graph.get("answer") else [])}
    aid = feedback.save_analysis(state["payload"], incident, {k: v for k, v in report.items() if k != "graph"},
                                 verdict, (graph or {}).get("query_id"))
    report["analysis_id"] = aid
    return report


def run_workflow(payload: dict) -> Iterator[dict]:
    """Stream the graph: yields agent_start / agent_done events as nodes run, then {"type": "result"}."""
    final: Dict[str, Any] = {}
    for mode, chunk in disruption_agent_graph.stream(_initial_state(payload), {"recursion_limit": RECURSION_LIMIT},
                                                     stream_mode=["custom", "values"]):
        if mode == "custom":
            yield chunk
        else:
            final = chunk
    g = final.get("guardrail_result") or {}
    if not g.get("is_valid", False):
        _raise_guardrail(g)
    yield {"type": "result", "data": _report(final)}


def run_sync(payload: dict) -> dict:
    """Run the whole workflow and return the final analysis."""
    state = disruption_agent_graph.invoke(_initial_state(payload), {"recursion_limit": RECURSION_LIMIT})
    g = state.get("guardrail_result") or {}
    if not g.get("is_valid", False):
        _raise_guardrail(g)
    return _report(state)


def ask_disruption_assistant(description: str, **options) -> Dict[str, Any]:
    """Top-level invocation function for the agent-based system."""
    return run_sync({"description": description, "use_graph": True, "judge": True, "top_k": 8, **options})
