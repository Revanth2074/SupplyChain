"""
Agent Copilot Query Routes.
Invokes the supervisor-led LangGraph agents (streamed over Server-Sent Events or returned whole)
and the RAG Q&A grounded in Synapt graph-RAG + hybrid retrieval.
"""

import concurrent.futures as cf
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from agents import run_sync, run_workflow
from agents import synapt_tools as syn
from agents.guardrails import validate_text
from agents.retrieval import hybrid_search
from schemas import AnalyzeRequest, AskRequest, compact
from services import feedback
from services.bootstrap import ready

router = APIRouter(tags=["Agent Copilot"])
log = logging.getLogger("api.query")
_pool = cf.ThreadPoolExecutor(max_workers=4)


def _payload(req: AnalyzeRequest) -> dict:
    payload = req.model_dump()
    payload["incident"] = compact(req.incident)
    payload["filters"] = compact(req.filters)
    return payload


@router.post("/analyze")
def analyze(req: AnalyzeRequest):
    """Run the supervisor-led agents and return the full analysis."""
    ready()
    try:
        return run_sync(_payload(req))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/analyze/stream")
def analyze_stream(req: AnalyzeRequest):
    """Server-Sent Events stream of the agents and the supervisor's routing decisions."""
    ready()
    payload = _payload(req)

    def gen():
        try:
            for ev in run_workflow(payload):
                yield f"data: {json.dumps(ev, default=str)}\n\n"
        except HTTPException as e:
            yield f"data: {json.dumps({'type': 'error', 'error': e.detail})}\n\n"
        except Exception as e:  # noqa: BLE001
            log.exception("workflow failed")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/ask")
def ask(req: AskRequest):
    """RAG Q&A: answer from Synapt graph-RAG (trident_query) with hybrid-retrieval sources."""
    ready()
    q = validate_text(req.question, "question")
    filters = compact(req.filters)
    gfut = _pool.submit(syn.fetch_synapt_rag, q["text"], req.top_k, None, 75, "ask")
    try:
        sres = hybrid_search(q["text"], filters, req.top_k)
        graph = gfut.result(timeout=80)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Synapt query failed: {e}") from e
    return {"question": q["text"], "answer": graph.get("answer") or "", "method": "synapt",
            "sources": sres["results"], "semantic_source": sres["semantic_source"], "graph": graph}


@router.get("/analyses")
def analyses(limit: int = 20):
    """Most recent saved analyses."""
    return feedback.recent_analyses(limit)


@router.get("/analyses/{aid}")
def get_analysis(aid: str):
    a = feedback.get_analysis(aid)
    if not a:
        raise HTTPException(404, "analysis not found")
    return a
