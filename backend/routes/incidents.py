"""
Incident Desk API Routes.
Opens incidents from an analysis, tracks SLA clocks and escalation, and records action outcomes
(closing an action with real figures turns it into training data and a Synapt feedback verdict).
"""

from fastapi import APIRouter, HTTPException

from schemas import ActionPatch, ActionRequest, IncidentPatch, IncidentRequest
from services import feedback, ops
from services.bootstrap import ready

router = APIRouter(tags=["Incident Desk"])


@router.get("/incidents")
def incidents_ep():
    return ops.list_incidents()


@router.post("/incidents")
def open_incident(req: IncidentRequest):
    a = feedback.get_analysis(req.analysis_id)
    if not a:
        raise HTTPException(404, "analysis not found")
    return {"id": ops.create_from_analysis(a)}


@router.post("/incidents/seed-demo")
def seed_incidents():
    ready()
    return {"created": ops.seed_demo()}


@router.patch("/incidents/{iid}")
def patch_incident(iid: str, req: IncidentPatch):
    try:
        ops.update_incident(iid, req.status, req.owner)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"id": iid}


@router.post("/incidents/{iid}/actions")
def add_incident_action(iid: str, req: ActionRequest):
    try:
        return {"id": ops.add_action(iid, req.title, req.owner, req.due_hours)}
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.patch("/actions/{aid}")
def patch_action(aid: str, req: ActionPatch):
    try:
        return ops.update_action(aid, req.status, req.actual_recovery_days, req.actual_loss_usd, req.notes)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
