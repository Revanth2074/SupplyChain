"""
Activity History Routes.
Server-side log of everything done in the console (stored in artifacts/history.json), so the
History tab shows the same entries on every device. Saved analyses re-open via GET /api/analyses/{id}.
"""

from fastapi import APIRouter, HTTPException

from schemas.history import KINDS, HistoryRequest
from services import history

router = APIRouter(tags=["History"])


@router.get("/history")
def list_history(kind: str | None = None, q: str | None = None, limit: int = 200):
    """Newest-first list of recorded actions with per-kind counts (snapshots omitted)."""
    return history.list_entries(kind, q, max(1, min(limit, 2000)))


@router.post("/history")
def add_history(req: HistoryRequest):
    """Records one action taken in the console."""
    if req.kind not in KINDS:
        raise HTTPException(422, f"Unknown kind '{req.kind}'. Allowed: {', '.join(KINDS)}")
    return history.record(req.kind, req.title, req.summary, req.data, req.ref)


@router.get("/history/{entry_id}")
def get_history(entry_id: str):
    """One entry including its stored inputs and result snapshot."""
    e = history.get(entry_id)
    if not e:
        raise HTTPException(404, "History entry not found")
    return e


@router.delete("/history/{entry_id}")
def delete_history(entry_id: str):
    if not history.delete(entry_id):
        raise HTTPException(404, "History entry not found")
    return {"deleted": entry_id}


@router.delete("/history")
def clear_history():
    """Removes every entry (the saved analyses themselves stay in feedback.db)."""
    return {"deleted": history.clear()}

