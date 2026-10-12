"""
Health Check & Metadata API Routes.
Reports service readiness, Synapt MCP connectivity, LLM (judge) configuration,
data and model status, and the dataset vocabulary for the console.
"""

from fastapi import APIRouter

from agents.prediction import registry
from agents import synapt_tools as syn
from agents.state import AGENTS
from config import settings
from services import llm
from services.bootstrap import boot, ready
from services.data_store import store

router = APIRouter(tags=["Health"])


@router.get("/health")
def health():
    """Health check endpoint verifying data, models, Synapt MCP and LLM status."""
    return {"status": boot["stage"], "error": boot["error"], "synapt": syn.status(),
            "llm": {"configured": llm.available(), "base_url": settings.LLM_BASE_URL, "model": settings.LLM_MODEL,
                    "judge_model": settings.JUDGE_MODEL},
            "data": {"ready": store.ready, "rows": int(len(store.df)) if store.df is not None else 0},
            "models": {"ready": registry.ready, "training": registry.training,
                       "trained_at": registry.meta.get("trained_at"), "fallback": registry.fallback()}}


@router.get("/meta")
def meta():
    """Dataset vocabulary (allowed field values) and the agents (supervisor + seven workers)."""
    ready()
    return {"options": store.options(), "agents": [{"id": a, "name": n, "description": d} for a, n, d in AGENTS]}
