"""
Operator Feedback API Route.
Records ratings, chosen strategies and real outcomes locally (strategy re-weighting and model
retraining) and writes the verdict into the Synapt Context Substrate via trident_feedback.
"""

import logging

from fastapi import APIRouter

from agents import synapt_tools as syn
from agents.guardrails import validate_text
from schemas import FeedbackRequest, FeedbackResponse
from services import analytics, feedback

router = APIRouter(tags=["Operator Feedback"])
log = logging.getLogger("api.feedback")


@router.post("/feedback", response_model=FeedbackResponse)
def record_feedback(req: FeedbackRequest):
    """Records operator rating and feedback; sends the verdict to Synapt via trident_feedback."""
    d = req.model_dump()
    if req.comment:
        d["comment"] = validate_text(req.comment, "comment", require_domain=False)["text"]
    a = feedback.get_analysis(req.analysis_id) if req.analysis_id else None
    if a:
        d["disruption_type"] = a["incident"].get("disruption_type")
        d["industry"] = a["incident"].get("industry")
        d["recommended_strategy"] = (a["report"].get("plan") or {}).get("primary_strategy")
        qid = a.get("synapt_query_id")
        if qid:
            try:
                verdict = "deflected" if req.rating >= 4 else "partial" if req.rating == 3 else "not_deflected"
                syn.send_feedback(qid, verdict, req.rating / 5, req.comment)
                d["synapt_sent"] = True
            except Exception as e:  # noqa: BLE001
                log.warning("Synapt feedback failed: %s", e)
    fid = feedback.add_feedback(d)
    analytics.insights.cache_clear()
    return FeedbackResponse(id=fid, synapt_sent=bool(d.get("synapt_sent")), boosts=len(feedback.strategy_boosts()))


@router.get("/feedback/stats")
def feedback_stats():
    return feedback.stats()
