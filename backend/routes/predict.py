"""
Prediction, Explainability & Model Routes (Requirement 2).
Production-impact / revenue-loss / recovery-time predictions with P10-P90 ranges, local and global
explanations, counterfactual what-if, model metrics and retraining from operator outcomes.
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException

from agents.guardrails import validate_incident
from agents.impact_analysis import priority
from agents.prediction import registry
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
    pred = registry.predict(d)
    return {"incident": d, "prediction": pred, "priority": priority(d, pred)}


@router.post("/explain")
def explain(inc: Incident):
    ready()
    d = _incident(inc)
    return {"incident": d, "explanation": registry.explain(d)}


@router.post("/whatif")
def whatif(inc: Incident):
    """Counterfactual analysis: how outcomes change if one lever (backup, response speed, tier,
    strategy) had been different."""
    ready()
    d = _incident(inc)
    if not d.get("disruption_type"):
        raise HTTPException(422, "disruption_type is required")
    return {"incident": d, **registry.whatif(d)}


@router.get("/models")
def models_info():
    """Validation metrics, feature importance and interval coverage of the trained models."""
    ready()
    return registry.meta


@router.post("/models/retrain")
def retrain(bg: BackgroundTasks):
    """Retrain the models with the real outcomes operators reported (feedback loop)."""
    ready()
    extra = feedback.outcome_rows()
    if registry.training:
        return {"status": "already training"}
    bg.add_task(registry.train, extra)
    return {"status": "retraining started", "feedback_rows": int(len(extra))}
