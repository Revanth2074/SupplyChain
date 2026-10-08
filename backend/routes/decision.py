"""
Decision Support Routes.
Scenario comparison in money (loss avoided vs cost of acting), root-cause chains, and the Synapt
knowledge graph's own explanation of the causal chain.
"""

from fastapi import APIRouter, HTTPException

from agents import synapt_tools as syn
from agents.guardrails import validate_incident
from schemas import DecisionRequest, Incident
from services import decision
from services.bootstrap import ready
from services.data_store import store

router = APIRouter(tags=["Decision Support"])


def _incident_dict(inc: Incident) -> dict:
    d = {k: v for k, v in inc.model_dump().items() if v is not None}
    validate_incident(d, store.options())
    if not d.get("disruption_type"):
        raise HTTPException(422, "disruption_type is required")
    return d


@router.post("/decision")
def decision_ep(req: DecisionRequest):
    """Compare response scenarios: predicted loss and recovery vs mitigation cost (ROI)."""
    ready()
    return decision.compare_scenarios(_incident_dict(req.incident), req.costs)


@router.post("/rootcause")
def rootcause_ep(inc: Incident):
    """How the disruption propagates (cause -> effects) and which factors made it worse or better."""
    ready()
    return decision.root_cause(_incident_dict(inc))


@router.post("/rootcause/synapt")
def rootcause_synapt(inc: Incident):
    """Ask the Synapt knowledge graph to explain the causal chain, with its evidence subgraph."""
    d = _incident_dict(inc)
    q = (f"For a {d['disruption_type']} disruption at a Tier {d.get('supplier_tier', 2)} {d.get('industry', '')} supplier"
         f"{' with no backup supplier' if d.get('has_backup_supplier') is False else ''}, what drives the production impact "
         f"and recovery time, and which response strategy recovers fastest?")
    try:
        return syn.fetch_synapt_rag(q, 6, None, 90, "rootcause")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Synapt query failed: {e}") from e
