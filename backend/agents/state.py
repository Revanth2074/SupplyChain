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
    ("supervisor", "Supervisor Agent", "Reads the shared state and decides which agent runs next, and when to stop"),
    ("intake", "Intake & Classification Agent", "Validates input and classifies the disruption"),
    ("investigator", "Investigation Agent", "Retrieves similar historical cases via Synapt hybrid + graph RAG"),
    ("impact", "Impact Assessment Agent", "Predicts production, financial & recovery impact; prioritises"),
    ("planner", "Response Planning Agent", "Ranks response strategies; plan from statistics + Synapt playbook"),
    ("recovery", "Recovery Analysis Agent", "Projects recovery timeline and resilience actions"),
    ("reporter", "Report Agent", "Builds the fact-checked briefing with the Synapt graph answer"),
    ("judge", "Judge Agent", "Audits the analysis for groundedness and quality (rule rubric)"),
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

    # Supervisor routing: its decisions (with reasons), the agents it chose, and the loop counters
    decisions: Annotated[List[Dict[str, Any]], operator.add]
    next_agents: List[str]
    routes: int
    retrieval_round: int
    retrieval_plan: Dict[str, Any]       # {"broaden": True} when the supervisor asks for wider retrieval
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
