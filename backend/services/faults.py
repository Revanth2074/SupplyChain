"""Fallback Lab: switch dependencies off at runtime to prove the fallbacks work.

Each switch simulates an outage at the lowest level (the Synapt client, the LLM wrapper, the model
registry, the live-feed fetch), so the normal error handling and fallbacks run exactly as they
would in a real outage. Switches restore themselves after a timeout so a demo cannot leave the
app degraded. Set ENABLE_FALLBACK_LAB=0 to hide the controls (switches can then not be turned on).
"""
from __future__ import annotations

import os
import threading
import time

ENABLED = os.getenv("ENABLE_FALLBACK_LAB", "1").lower() not in ("0", "false", "no")
MAX_MINUTES = 120

SWITCHES = {
    "synapt": {
        "label": "Synapt (all tools)",
        "outage": "Every Synapt MCP call fails as if the server were unreachable.",
        "fallback": "Case search uses the local LSA index; graph answer, playbooks, episodes and Synapt "
                    "labels are skipped; feedback is kept locally.",
    },
    "synapt_graph": {
        "label": "Synapt graph-RAG only",
        "outage": "Only trident_query (graph-RAG) fails; chunks and playbooks keep working.",
        "fallback": "The briefing has no Synapt graph answer and /ask returns extractive case snippets.",
    },
    "synapt_procedures": {
        "label": "Synapt playbooks only",
        "outage": "Only trident_get_procedures fails.",
        "fallback": "The planner ranks strategies from historical statistics without the SOP steps.",
    },
    "llm": {
        "label": "LLM judge (aicredits.in)",
        "outage": "The external judge LLM fails. It is used only for evaluation (LLM-as-judge, DeepEval).",
        "fallback": "The workflow is unaffected (it never calls the LLM); judging falls back to the rule rubric.",
    },
    "ml": {
        "label": "Prediction models",
        "outage": "The trained gradient-boosting models are treated as unavailable.",
        "fallback": "Predictions, ranges and risk come from statistics of the most similar historical cohort "
                    "(median and P10/P90 of cases with the same severity, tier, backup, size, ...).",
    },
    "live_feed": {
        "label": "Live hazard feed (GDACS)",
        "outage": "Fetching live hazard alerts fails.",
        "fallback": "Early warning keeps working on stored and manual signals; the fetch reports a clear error.",
    },
}

_lock = threading.Lock()
_until: dict[str, float] = {}   # switch -> time it restores itself
_listeners: list = []            # called with (name, enabled) after a change


class SimulatedOutage(RuntimeError):
    pass


def active(name: str) -> bool:
    t = _until.get(name)
    if t is None:
        return False
    if time.time() >= t:
        set_switch(name, False)
        return False
    return True


def active_list() -> list[str]:
    return [n for n in SWITCHES if active(n)]


def check(name: str, what: str | None = None) -> None:
    if active(name):
        raise SimulatedOutage(f"Simulated outage: {what or SWITCHES[name]['label']} switched off in the Fallback Lab")


def check_synapt(tool: str) -> None:
    check("synapt", f"Synapt ({tool})")
    if tool == "trident_query":
        check("synapt_graph", "Synapt graph-RAG")
    if tool == "trident_get_procedures":
        check("synapt_procedures", "Synapt playbooks")


def on_change(fn) -> None:
    _listeners.append(fn)


def set_switch(name: str, enabled: bool, minutes: float = 30) -> None:
    if name not in SWITCHES:
        raise KeyError(name)
    if enabled and not ENABLED:
        raise PermissionError("Fallback Lab is disabled (ENABLE_FALLBACK_LAB=0)")
    with _lock:
        was = name in _until
        if enabled:
            _until[name] = time.time() + 60 * max(1.0, min(float(minutes), MAX_MINUTES))
        else:
            _until.pop(name, None)
    if was != enabled:
        for fn in _listeners:
            fn(name, enabled)


def reset() -> None:
    for n in list(_until):
        set_switch(n, False)


def status() -> dict:
    now = time.time()
    return {"enabled": ENABLED, "max_minutes": MAX_MINUTES,
            "switches": [{"id": n, **meta, "active": active(n),
                          "restores_in_s": int(_until[n] - now) if n in _until else None}
                         for n, meta in SWITCHES.items()]}
