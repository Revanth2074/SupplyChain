"""
Operations Statistics Routes.
One-screen overview for the home page and historical factor insights across all 100,000 disruptions.
"""

from fastapi import APIRouter

from agents.prediction import registry
from agents import synapt_tools as syn
from routes.portfolio import scored_portfolio
from services import analytics, feedback, ops, risk_watch
from services.bootstrap import ready
from services.data_store import store

router = APIRouter(tags=["Statistics"])


@router.get("/overview")
def overview():
    """One-screen status for the home page: what the assistant watches and what needs attention."""
    ready()
    scored = scored_portfolio(None)
    sigs = risk_watch.list_signals(active_only=True)
    ew = risk_watch.early_warning(scored, sigs)
    incs = ops.list_incidents()
    open_incs = [i for i in incs if i["status"] != "resolved"]
    fb = feedback.stats()
    q = feedback.synapt_quality()
    return {
        "cases": int(len(store.df)), "suppliers": scored["count"], "signals_active": len(sigs),
        "early_warning": ew["levels"], "top_risks": ew["suppliers"][:3],
        "incidents_open": len(open_incs), "sla_breached": sum(i["breached"] for i in open_incs),
        "escalated": sum(i["escalated"] for i in open_incs),
        "actions_open": sum(1 for i in open_incs for a in i["actions"] if a["status"] not in ("done", "rejected")),
        "feedback": {"total": fb["total"], "with_outcomes": fb["with_outcomes"], "avg_rating": fb["avg_rating"]},
        "synapt": {**syn.status(), "answers": q["n"], "avg_confidence": q["summary"].get("confidence")},
        "models": {k: v.get("r2") for k, v in registry.meta.get("targets", {}).items() if "r2" in v},
    }


@router.get("/insights")
def insights():
    """What drives bigger losses and slower recovery, grouped by every dataset factor."""
    ready()
    return analytics.insights()
