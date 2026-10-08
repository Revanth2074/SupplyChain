"""
LangGraph Multi-Agent Orchestration Graph.
Wires the Guardrails, Classifier (Intake), Hybrid Retriever, Synapt Worker, Evidence Fusion,
Impact, Planner, Recovery, Synthesis (Report) and Judge nodes into a stateful, compiled StateGraph.

    START -> guardrails --(invalid)--> END
                 |
              classifier
               /      \\
   hybrid_retriever   synapt_worker        (run in parallel)
               \\      /
            evidence_fusion -> impact_analyzer -> planner -> recovery -> synthesis -> judge -> END

Each node streams agent_start / agent_done events (stream_mode="custom") that the console
shows live over Server-Sent Events.
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
from agents.synapt_tools import synapt_worker_node
from agents.synthesis import synthesis_node
from services import feedback


def guardrail_decision(state: DisruptionAgentState) -> Literal["classifier", "__end__"]:
    """Conditional routing based on input guardrail checks."""
    guardrail = state.get("guardrail_result")
    if guardrail and not guardrail.get("is_valid", True):
        return END
    return "classifier"


def build_disruption_agent_graph():
    """Builds and compiles the multi-agent StateGraph."""
    workflow = StateGraph(DisruptionAgentState)

    # 1. Add All Agent Nodes
    workflow.add_node("guardrails", guardrails_node)
    workflow.add_node("classifier", classifier_node)
    workflow.add_node("hybrid_retriever", hybrid_retrieval_node)
    workflow.add_node("synapt_worker", synapt_worker_node)
    workflow.add_node("evidence_fusion", evidence_fusion_node)
    workflow.add_node("impact_analyzer", impact_analysis_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("recovery", recovery_node)
    workflow.add_node("synthesis", synthesis_node)
    workflow.add_node("judge", judge_node)

    # 2. Entry: START -> guardrails -> classifier OR END
    workflow.add_edge(START, "guardrails")
    workflow.add_conditional_edges("guardrails", guardrail_decision, {"classifier": "classifier", END: END})

    # 3. Classifier fans out: local hybrid retrieval and the Synapt worker run in parallel
    workflow.add_edge("classifier", "hybrid_retriever")
    workflow.add_edge("classifier", "synapt_worker")

    # 4. Both branches join in evidence fusion
    workflow.add_edge(["hybrid_retriever", "synapt_worker"], "evidence_fusion")

    # 5. Impact -> Planner -> Recovery -> Synthesis -> Judge -> END
    workflow.add_edge("evidence_fusion", "impact_analyzer")
    workflow.add_edge("impact_analyzer", "planner")
    workflow.add_edge("planner", "recovery")
    workflow.add_edge("recovery", "synthesis")
    workflow.add_edge("synthesis", "judge")
    workflow.add_edge("judge", END)

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
    for mode, chunk in disruption_agent_graph.stream(_initial_state(payload), stream_mode=["custom", "values"]):
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
    state = disruption_agent_graph.invoke(_initial_state(payload))
    g = state.get("guardrail_result") or {}
    if not g.get("is_valid", False):
        _raise_guardrail(g)
    return _report(state)


def ask_disruption_assistant(description: str, **options) -> Dict[str, Any]:
    """Top-level invocation function for the multi-agent system."""
    return run_sync({"description": description, "use_graph": True, "judge": True, "top_k": 8, **options})
