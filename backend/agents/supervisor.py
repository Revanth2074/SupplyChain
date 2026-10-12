"""
Supervisor Agent.
Agent-based orchestration on a shared blackboard. The supervisor does not hard-code an order: it holds
a set of GOALS, each owned by an agent, with the inputs the goal depends on and a test for when it is
achieved. After every step control returns here and the supervisor

  1. acts on requests the agents posted in their messages (e.g. the Judge asking the Planner to re-plan
     because "consistency" scored low), within per-request budgets, resetting the outputs that must be
     recomputed so the dependent goals re-open by themselves;
  2. keeps a safety backstop: a briefing that still fails the fact-check after the Report agent's own
     rewrites goes back once more in strict mode;
  3. otherwise schedules every agent whose goal is open and whose inputs are ready, all in parallel
     (e.g. case search, the Synapt agent and impact prediction start together);
  4. finishes when every goal is met, and always stops at MAX_ROUTES decisions.

Each decision carries a stated reason that is streamed to the console and saved with the report.
The worker agents decide for themselves how to reach their own goal (see agents/base.py).
"""

from __future__ import annotations

from typing import Any, Callable

from agents.state import emit

MAX_ROUTES = 25          # hard stop for the routing loop
MAX_REVISIONS = 1        # Judge-requested redo rounds
MAX_REPORT_ROUNDS = 2    # supervisor-level strict rewrites of a briefing that still fails the fact-check

FINISH = "__end__"

S = dict


def _judge_on(s: S) -> bool:
    return (s.get("payload") or {}).get("judge", True)


# (goal, owning agent, inputs ready?, achieved?)
GOALS: list[tuple[str, str, Callable[[S], bool], Callable[[S], bool]]] = [
    ("classify the incident", "classifier",
     lambda s: True, lambda s: s.get("incident") is not None),
    ("find similar precedents", "hybrid_retriever",
     lambda s: s.get("incident") is not None, lambda s: s.get("search") is not None),
    ("get Synapt's graph-RAG answer and playbook", "synapt_worker",
     lambda s: s.get("incident") is not None, lambda s: s.get("synapt_round", 0) > 0),
    ("predict impact and priority", "impact_analyzer",
     lambda s: s.get("incident") is not None, lambda s: s.get("impact") is not None),
    ("merge the evidence", "evidence_fusion",
     lambda s: s.get("search") is not None and s.get("synapt_round", 0) > 0, lambda s: s.get("cases") is not None),
    ("build the response plan", "planner",
     lambda s: s.get("cases") is not None and s.get("impact") is not None, lambda s: s.get("plan") is not None),
    ("project recovery", "recovery",
     lambda s: s.get("plan") is not None, lambda s: s.get("recovery") is not None),
    ("write the fact-checked briefing", "synthesis",
     lambda s: all(s.get(k) is not None for k in ("recovery", "impact", "plan", "cases")), lambda s: s.get("summary") is not None),
    ("audit the analysis", "judge",
     lambda s: s.get("summary") is not None, lambda s: not _judge_on(s) or s.get("verdict") is not None),
]


def _requests(state: S) -> list[dict]:
    """Requests posted in messages the supervisor has not acted on yet."""
    msgs = state.get("messages") or []
    out = []
    for m in msgs[state.get("msg_cursor", 0):]:
        for r in m.get("requests") or []:
            out.append({**r, "from": m["agent"]})
    return out


def decide(state: S) -> tuple[list[str], str, dict[str, Any]]:
    """Routing policy: (next agents, reason, state updates). An empty agent list means finish."""
    if state.get("routes", 0) >= MAX_ROUTES:
        return [], f"Stopping: routing limit of {MAX_ROUTES} decisions reached", {}
    cursor = {"msg_cursor": len(state.get("messages") or [])}

    # 1. Requests from agents (the Judge's targeted "revise")
    for req in _requests(state):
        if req["from"] == "judge" and state.get("revision", 0) >= MAX_REVISIONS:
            continue  # budget spent: the analysis is reported as it stands
        upd = {k: None for k in req.get("reset", [])}
        upd.update(req.get("params") or {})
        upd.update(cursor, revision=state.get("revision", 0) + (req["from"] == "judge"))
        return [req["to"]], f"{req['from'].capitalize()} asks for a redo: {req['reason']}", upd

    # 2. Backstop: a briefing that still fails the fact-check after the Report agent's own rewrites
    fc = state.get("fact_check") or {}
    if (state.get("summary") is not None and fc and not fc.get("passed", True)
            and state.get("report_round", 0) < MAX_REPORT_ROUNDS):
        return (["synthesis"], f"Fact-check still flags {len(fc.get('final') or [])} figure(s) after the Report agent's "
                "rewrites: send it back once more in strict mode", {**cursor, "summary": None, "verdict": None, "report_mode": "strict"})

    # 3. Every open goal whose inputs are ready, in parallel
    ready = [(g, a) for g, a, inputs, achieved in GOALS if not achieved(state) and inputs(state)]
    if ready:
        agents = [a for _, a in ready]
        goals = "; ".join(g for g, _ in ready)
        how = "in parallel" if len(agents) > 1 else "next"
        return agents, f"Open goal{'s' if len(agents) > 1 else ''} with inputs ready, run {how}: {goals}", cursor

    # 4. Done
    verdict = state.get("verdict")
    if verdict:
        why = f"Judge verdict {verdict.get('verdict', '?').upper()} ({verdict.get('overall_score', 0):.0%})"
        if verdict.get("verdict") == "revise" and state.get("revision", 0) >= MAX_REVISIONS:
            why += " after the revision budget was used"
        return [], f"All goals met. {why}: analysis complete", cursor
    return [], "All goals met (judge audit not requested): analysis complete", cursor


def supervisor_node(state: S) -> S:
    """LangGraph node (Supervisor agent): decide the next agent(s) and record why."""
    nxt, reason, updates = decide(state)
    n = state.get("routes", 0) + 1
    decision = {"step": n, "next": nxt or ["finish"], "reason": reason}
    emit("route", "supervisor", **decision)
    return {**updates, "next_agents": nxt, "routes": n, "decisions": [decision]}


def route(state: S) -> list[str] | str:
    """Conditional edge out of the supervisor: the agent(s) it chose, or END."""
    return state.get("next_agents") or FINISH
