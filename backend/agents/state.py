"""
Supply-Chain Disruption Assistant — Agent State Schema.
Defines the typed dictionary state shared by the supervisor and all agents, the user-facing
agents, and the progress-event helper used for SSE streaming.
"""

from __future__ import annotations

import operator
import time
from typing import Annotated, Any, Dict, List, Optional, TypedDict

# The agents the console shows. Graph nodes report progress under these ids.
AGENTS = [
    ("supervisor", "Supervisor Agent", "Schedules agents by goal and dependency, acts on their requests, decides when to stop"),
    ("intake", "Intake & Classification Agent", "Classifies the disruption; asks Synapt to label fields it is unsure of"),
    ("investigator", "Investigation Agent", "Searches until the evidence is strong enough; queries Synapt graph-RAG + playbook"),
    ("impact", "Impact Assessment Agent", "Predicts impact, cross-checks it against similar cases, prioritises"),
    ("planner", "Response Planning Agent", "Ranks strategies, rejects weakly supported ones, follows the Synapt playbook"),
    ("recovery", "Recovery Analysis Agent", "Projects the recovery timeline and checks it against the cohort"),
    ("reporter", "Report Agent", "Drafts the briefing, fact-checks it and rewrites until it passes"),
    ("judge", "Judge Agent", "Audits six criteria; asks the right agent to redo its part when one is weak"),
]
AGENT_NAMES = {a: n for a, n, _ in AGENTS}


class DisruptionAgentState(TypedDict, total=False):
    # Request
    payload: Dict[str, Any]          # description, incident, filters, top_k, use_graph, judge
    started_at: float

    # Intake: guardrails + classification
    guardrail_result: Dict[str, Any]  # is_valid, status, message
    description: str
    given_incident: Dict[str, Any]
    warnings: List[str]
    incident: Dict[str, Any]
    classification: Dict[str, Any]
    query: str
    intake_t0: float

    # Investigation: hybrid retrieval and the Synapt worker (the supervisor may run them in parallel)
    investigation_t0: float
    search: Dict[str, Any]
    graph: Optional[Dict[str, Any]]       # trident_query answer, subgraph, quality
    procedure: Optional[Dict[str, Any]]   # trident_get_procedures playbook
    cases: List[Dict[str, Any]]

    # Analysis & planning
    impact: Dict[str, Any]
    strategies: Dict[str, Any]
    evidence_cases: List[Dict[str, Any]]
    plan: Dict[str, Any]
    recovery: Dict[str, Any]

    # Synthesis & audit
    summary: str
    facts: Dict[str, Any]
    fact_check: Dict[str, Any]
    verdict: Optional[Dict[str, Any]]

    # Agent messages on the blackboard: status, confidence, summary, steps and requests for other agents
    messages: Annotated[List[Dict[str, Any]], operator.add]
    msg_cursor: int                      # how many messages the supervisor has already acted on
    report_mode: str                     # "strict" when the supervisor asks the Report agent for a strict rewrite
    plan_hint: Dict[str, Any]            # e.g. {"exclude": [...]} when the Judge asks the Planner to reconsider

    # Supervisor routing: its decisions (with reasons), the agents it chose, and the loop counters
    decisions: Annotated[List[Dict[str, Any]], operator.add]
    next_agents: List[str]
    routes: int
    retrieval_round: int
    retrieval_plan: Dict[str, Any]       # {"broaden": True} / {"focus": True} when the supervisor asks for another search
    synapt_round: int
    report_round: int
    revision: int

    # Per-agent timings/summaries (parallel nodes append, so the list has a reducer)
    trace: Annotated[List[Dict[str, Any]], operator.add]


def describe(inc: dict) -> str:
    """One-line description of an incident, used in queries and summaries."""
    parts = [f"{inc.get('disruption_type', 'Unknown')} disruption"]
    if inc.get("industry"):
        parts.append(f"in {inc['industry']}")
    if inc.get("supplier_tier"):
        parts.append(f"Tier {inc['supplier_tier']} supplier")
    if inc.get("supplier_region"):
        parts.append(f"in {inc['supplier_region']}")
    if inc.get("supplier_size"):
        parts.append(f"({inc['supplier_size']})")
    if inc.get("has_backup_supplier") is not None:
        parts.append("with backup supplier" if inc["has_backup_supplier"] else "with no backup supplier")
    if inc.get("disruption_severity"):
        parts.append(f"severity {inc['disruption_severity']}/5")
    return ", ".join(parts)


def emit(kind: str, agent: str, **kw) -> None:
    """Send a progress event (agent_start / agent_done) to the SSE stream; no-op outside streaming."""
    try:
        from langgraph.config import get_stream_writer
        writer = get_stream_writer()
    except Exception:  # noqa: BLE001  (called outside a graph run)
        return
    writer({"type": kind, "agent": agent, "name": AGENT_NAMES.get(agent, agent), "ts": time.time(), **kw})


def done(agent: str, t0: float, summary: str, data: Any) -> Dict[str, Any]:
    """Emit agent_done and return the trace entry for the state."""
    ms = int((time.time() - t0) * 1000)
    emit("agent_done", agent, ms=ms, summary=summary, data=data)
    return {"agent": agent, "ms": ms, "summary": summary}
