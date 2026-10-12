"""
Service Bootstrap & Readiness.
Connects to Synapt, then loads the 100k-case store and the prediction models in a background thread
at start-up, so the API answers /api/health immediately and other endpoints return 503 until ready.
Synapt is required: if it is not configured or unreachable, start-up stops in the "error" stage.
"""

from __future__ import annotations

import logging
import threading

from fastapi import HTTPException

from agents import synapt_tools as syn
from agents.prediction import registry
from services import feedback, ops, risk_watch
from services.data_store import store

log = logging.getLogger("bootstrap")

boot = {"stage": "starting", "error": None}


def _bootstrap() -> None:
    try:
        boot["stage"] = "connecting to Synapt"
        syn.require_configured()
        syn.get_synapt_connector()  # authenticate + MCP handshake
        boot["stage"] = "loading data"
        store.load()
        feedback.init()
        boot["stage"] = "loading/training models"
        registry.load_or_train()
        boot["stage"] = "ready"
    except Exception as e:  # noqa: BLE001
        log.exception("bootstrap failed")
        boot.update(stage="error", error=str(e))


def startup() -> None:
    """Create the SQLite tables, then load data and models without blocking the server."""
    feedback.init()
    ops.init()
    risk_watch.init()
    threading.Thread(target=_bootstrap, daemon=True).start()


def ready() -> None:
    """Raise 503 while the data and models are still loading."""
    if boot["stage"] != "ready":
        raise HTTPException(503, f"Service warming up: {boot['stage']}")
