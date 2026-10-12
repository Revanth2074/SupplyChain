"""
Agent Framework.
Every worker in the workflow is a goal-driven agent (no LLM). An agent has:

  * a goal          - what "done" means for it, checked against what it has observed
  * tools           - named capabilities it may call (Synapt MCP tools, search, ML models, checks)
  * a policy        - `decide()`: given what it has observed so far, pick the next tool and say why,
                      or stop because the goal is met or no tool can improve the result
  * a scratchpad    - every step (thought -> tool -> observation) is kept and streamed live
  * reflection      - `reflect()`: grade its own result (status, confidence) against the goal
  * a message       - what it reports back to the supervisor, including requests for other agents

    perceive(state) -> [ decide -> act (tool) -> observe ]* -> reflect -> commit(state updates)

The supervisor reads the agents' messages on the shared state (a blackboard) and decides what runs
next, so agents can ask for help (e.g. the Judge asks the Planner to re-plan) without calling each
other directly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from agents.state import done, emit


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable[..., Any]
    soft: bool = False   # soft tools may fail: the failure becomes an observation instead of an error


@dataclass
class Action:
    tool: str
    args: dict = field(default_factory=dict)
    thought: str = ""


class Agent:
    """Base class: subclasses define the goal, tools and the decide / observe / reflect / commit hooks."""

    id = ""              # id the console shows the agent under (intake, investigator, impact, ...)
    node = ""            # LangGraph node name
    goal = ""
    max_steps = 5
    reports_done = True  # False for agents whose result is reported by a later agent of the same id

    def __init__(self) -> None:
        self.tools = {t.name: t for t in self.make_tools()}

    # ---------------------------------------------------------------- hooks for subclasses
    def make_tools(self) -> list[Tool]:
        return []

    def perceive(self, state: dict) -> dict:
        """Build the agent's working memory from the shared state."""
        return {}

    def decide(self, obs: dict, steps: list[dict]) -> Action | None:
        """Next action, or None when the goal is met (or nothing can improve the result)."""
        return None

    def observe(self, obs: dict, action: Action, result: Any, error: str | None) -> dict:
        """Fold a tool result into the working memory."""
        return obs

    def summarise(self, action: Action, result: Any, error: str | None) -> str:
        """One-line observation shown in the console for a step."""
        return error or "ok"

    def reflect(self, obs: dict, steps: list[dict]) -> dict:
        """Self-assessment against the goal: {status, confidence, summary, requests}."""
        return {"status": "done", "confidence": None, "summary": "done", "requests": []}

    def commit(self, obs: dict, message: dict, state: dict) -> dict:
        """State updates this agent writes to the blackboard."""
        return {}

    def detail(self, obs: dict) -> Any:
        """Payload attached to the agent_done event (shown by the console)."""
        return None

    def started_at(self, state: dict) -> float:
        return time.time()

    # ---------------------------------------------------------------- the agent loop
    def __call__(self, state: dict) -> dict:
        t0 = self.started_at(state)
        emit("agent_start", self.id, node=self.node, goal=self.goal)
        obs = self.perceive(state)
        steps: list[dict] = []
        for i in range(self.max_steps):
            action = self.decide(obs, steps)
            if action is None:
                break
            tool = self.tools[action.tool]
            t1 = time.time()
            result, error = None, None
            try:
                result = tool.fn(**action.args)
            except Exception as e:  # noqa: BLE001
                if not tool.soft:
                    raise
                error = f"{type(e).__name__}: {str(e)[:160]}"
            step = {"node": self.node, "step": i + 1, "thought": action.thought, "tool": action.tool,
                    "ok": error is None, "ms": int((time.time() - t1) * 1000),
                    "observation": self.summarise(action, result, error)}
            steps.append(step)
            emit("agent_step", self.id, **step)
            obs = self.observe(obs, action, result, error)
        msg = self.reflect(obs, steps)
        message = {"agent": self.id, "node": self.node, "goal": self.goal, "status": msg.get("status", "done"),
                   "confidence": msg.get("confidence"), "summary": msg.get("summary", ""),
                   "requests": msg.get("requests", []), "steps": steps}
        updates = self.commit(obs, message, state)
        updates["messages"] = [message]
        if self.reports_done:
            entry = done(self.id, t0, message["summary"], {"message": {k: v for k, v in message.items() if k != "steps"},
                                                           "steps": steps, "result": self.detail(obs)})
            entry.update(steps=len(steps), confidence=message["confidence"], status=message["status"])
            updates["trace"] = [entry]
        return updates
