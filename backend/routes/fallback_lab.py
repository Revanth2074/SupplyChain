"""
Fallback Lab API Routes.
Switch dependencies off (Synapt, its graph or playbooks, the LLM, the models, the live feed) to
simulate outages, and run the self-test that checks every feature used the expected engine.
"""

from fastapi import APIRouter, HTTPException

from agents.prediction import registry
from agents import synapt_tools as syn
from schemas import SelfTestRequest, SwitchRequest
from services import fallback_lab, faults, llm
from services.bootstrap import ready

router = APIRouter(prefix="/fallback-lab", tags=["Fallback Lab"])


@router.get("")
def fallback_lab_status():
    """Outage switches (with what fails and what takes over) and the current Synapt breaker state."""
    return {**faults.status(), "synapt": syn.status(), "llm_configured": llm.available(),
            "models_fallback": registry.fallback()}


@router.put("/{name}")
def fallback_lab_switch(name: str, req: SwitchRequest):
    """Simulate an outage of one dependency (enabled=true) or restore it. Restores itself after `minutes`."""
    try:
        faults.set_switch(name, req.enabled, req.minutes)
    except KeyError as e:
        raise HTTPException(404, f"Unknown switch '{name}'. Options: {list(faults.SWITCHES)}") from e
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    return fallback_lab_status()


@router.post("/reset")
def fallback_lab_reset():
    faults.reset()
    return fallback_lab_status()


@router.post("/selftest")
def fallback_lab_selftest(req: SelfTestRequest):
    """Run every feature once; each check passes when it answered via the expected engine."""
    ready()
    return fallback_lab.run(req.full_workflow)
