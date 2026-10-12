"""
Hybrid Search, Classification, Recommendation & Prioritisation Routes (Requirement 1 core).
"""

from typing import Optional

from fastapi import APIRouter, HTTPException

from agents.classifier import classify as classify_text
from agents.guardrails import validate_incident, validate_text
from agents.impact_analysis import priority
from agents.planner import strategy_table
from agents.precedent import estimator
from agents.retrieval import hybrid_search
from agents.state import describe
from schemas import AnalyzeRequest, ClassifyRequest, Incident, PrioritizeRequest, SearchRequest, compact
from services.bootstrap import ready
from services.data_store import store

router = APIRouter(tags=["Search & Triage"])


def _resolve_incident(description: Optional[str], incident: Optional[Incident]) -> dict:
    given = {k: v for k, v in (incident.model_dump() if incident else {}).items() if v not in (None, "")}
    validate_incident(given, store.options())
    if description:
        v = validate_text(description, "description")
        cls = classify_text(v["text"])
        given = {**cls["fields"], **given}
    if not given.get("disruption_type"):
        raise HTTPException(422, "Could not determine disruption_type; provide it or a richer description")
    return given


@router.post("/search")
def search(req: SearchRequest):
    """Hybrid search: Synapt semantic + BM25 keyword (+ profile leg), fused with RRF, metadata-filtered."""
    ready()
    q = validate_text(req.query, "query")
    res = hybrid_search(q["text"], compact(req.filters), req.top_k, req.mode, alpha=req.alpha)
    res["warnings"] = q["warnings"]
    return res


@router.post("/classify")
def classify(req: ClassifyRequest):
    """Classification agent: free text -> structured disruption fields with confidence."""
    ready()
    v = validate_text(req.description, "description")
    res = classify_text(v["text"])
    res["warnings"] = v["warnings"]
    return res


@router.post("/recommend")
def recommend(req: AnalyzeRequest):
    """Lightweight recommendation (no multi-agent) based on historical strategy effectiveness."""
    ready()
    inc = _resolve_incident(req.description, req.incident)
    strat = strategy_table(inc)
    sim = hybrid_search(req.description or describe(inc), compact(req.filters), req.top_k, reference=inc)
    top = strat["strategies"][0] if strat["strategies"] else None
    return {"incident": inc, "recommended_strategy": top, "alternatives": strat["strategies"][1:3],
            "cohort": strat["scope"], "cohort_size": strat["n"], "similar_cases": sim["results"],
            "semantic_source": sim["semantic_source"]}


@router.post("/prioritize")
def prioritize(req: PrioritizeRequest):
    """Rank several incidents by severity, predicted production impact, financial loss and risk."""
    ready()
    opts = store.options()
    out = []
    for i, inc in enumerate(req.incidents):
        d = {k: v for k, v in inc.model_dump().items() if v is not None}
        validate_incident(d, opts)
        pred = estimator.predict(d)
        p = priority(d, pred)
        out.append({"index": i, "label": d.get("label") or f"Incident {i + 1}", "incident": d, "priority": p,
                    "prediction": {k: pred[k] for k in ("production_impact_pct", "revenue_loss_usd",
                                                        "full_recovery_days", "risk_level", "risk_probability")}})
    out.sort(key=lambda r: -r["priority"]["score"])
    for rank, r in enumerate(out, 1):
        r["rank"] = rank
    return {"count": len(out), "ranked": out}
