"""
Early Warning & External Signals Routes.
Forward-looking supplier risk from external signals (live GDACS feed + manual alerts), operational
health and ML impact-if-disrupted; signals can be pushed into Synapt as dated alert documents.
"""

from fastapi import APIRouter, HTTPException

from routes.portfolio import scored_portfolio
from schemas import PortfolioCsvRequest, SignalPatch, SignalRequest
from services import risk_watch
from services.bootstrap import ready

router = APIRouter(tags=["Early Warning"])


@router.post("/early-warning")
def early_warning_ep(req: PortfolioCsvRequest):
    """Forward-looking supplier risk: external signals + operational health + ML impact-if-disrupted."""
    ready()
    scored = scored_portfolio(req.csv, req.severity)
    sigs = risk_watch.list_signals(active_only=True)
    return {**risk_watch.early_warning(scored, sigs), "signals": risk_watch.signal_impacts(scored, sigs)}


@router.get("/signals")
def signals_ep():
    return risk_watch.list_signals()


@router.post("/signals")
def add_signal(req: SignalRequest):
    ready()
    try:
        return risk_watch.add_manual(req.headline, req.detail or "", req.send_to_synapt)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/signals/fetch-live")
def fetch_live_signals():
    """Pull current orange/red alerts from the public GDACS disaster feed."""
    try:
        return risk_watch.fetch_gdacs()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Live feed unavailable: {e}") from e


@router.patch("/signals/{sid}")
def patch_signal(sid: str, req: SignalPatch):
    risk_watch.set_active(sid, req.active)
    return {"id": sid, "active": req.active}


@router.post("/signals/{sid}/synapt")
def signal_to_synapt(sid: str):
    """Ingest the signal into the Synapt knowledge base (trident_ingest, 30-day TTL)."""
    try:
        return risk_watch.push_to_synapt(sid)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
