"""
Prediction, Explainability & Precedent Routes (Requirement 2).
Production-impact / revenue-loss / recovery-time estimates with P10-P90 ranges from comparable past
cases (no trained model), the nearest Synapt precedents, drivers, counterfactual what-if, the hold-out
check of the estimator and a refresh that adds the outcomes operators reported.
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException

from agents.guardrails import validate_incident
from agents.impact_analysis import priority
from agents.precedent import estimator
from schemas import Incident
from services import feedback
from services.bootstrap import ready
from services.data_store import store

router = APIRouter(tags=["Prediction & Explainability"])


def _incident(inc: Incident) -> dict:
    d = {k: v for k, v in inc.model_dump().items() if v is not None}
    validate_incident(d, store.options())
    return d


@router.post("/predict")
def predict(inc: Incident):
    ready()
    d = _incident(inc)
    pred = estimator.predict(d, synapt=True)
    return {"incident": d, "prediction": pred, "priority": priority(d, pred)}


@router.post("/explain")
def explain(inc: Incident):
    ready()
    d = _incident(inc)
    return {"incident": d, "explanation": estimator.explain(d)}


@router.post("/whatif")
def whatif(inc: Incident):
    """Counterfactual analysis: how outcomes change if one lever (backup, response speed, tier,
    strategy) had been different."""
    ready()
    d = _incident(inc)
    if not d.get("disruption_type"):
        raise HTTPException(422, "disruption_type is required")
    return {"incident": d, **estimator.whatif(d)}


@router.get("/precedent")
def precedent_info():
    """How the estimates are made: the precedent pool, cohort keys, how much each attribute separates
    outcomes, and the hold-out check (scripts/validate_precedent.py)."""
    ready()
    return estimator.meta


@router.post("/precedent/refresh")
def refresh(bg: BackgroundTasks):
    """Rebuild the precedent pool with the real outcomes operators reported (feedback loop)."""
    ready()
    extra = feedback.outcome_rows()
    if estimator.refreshing:
        return {"status": "already refreshing"}
    bg.add_task(estimator.load, extra)
    return {"status": "refresh started", "feedback_rows": int(len(extra))}
