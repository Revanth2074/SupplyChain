"""
Server Routes Package.
Exports API routers for inclusion into the main FastAPI application.
"""

from routes.decision import router as decision_router
from routes.evaluation import router as evaluation_router
from routes.fallback_lab import router as fallback_lab_router
from routes.feedback import router as feedback_router
from routes.health import router as health_router
from routes.history import router as history_router
from routes.incidents import router as incidents_router
from routes.portfolio import router as portfolio_router
from routes.predict import router as predict_router
from routes.query import router as query_router
from routes.search import router as search_router
from routes.signals import router as signals_router
from routes.sops import router as sops_router
from routes.stats import router as stats_router
from routes.synapt import router as synapt_router

__all__ = [
    "health_router",
    "query_router",
    "search_router",
    "predict_router",
    "decision_router",
    "portfolio_router",
    "signals_router",
    "incidents_router",
    "stats_router",
    "synapt_router",
    "sops_router",
    "feedback_router",
    "evaluation_router",
    "fallback_lab_router",
    "history_router",
]
