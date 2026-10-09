"""
Agent Copilot Query Routes.
Invokes the LangGraph multi-agent workflow (streamed over Server-Sent Events or returned whole)
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
    """Run the 7-agent workflow and return the full analysis."""
    ready()
    try:
        return run_sync(_payload(req))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/analyze/stream")
def analyze_stream(req: AnalyzeRequest):
    """Server-Sent Events stream of the multi-agent workflow."""
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
    gfut = _pool.submit(syn.fetch_synapt_rag, q["text"], req.top_k, None, 75, "ask") \
        if (req.use_graph and syn.configured()) else None
    sres = hybrid_search(q["text"], filters, req.top_k)
    graph = None
    if gfut:
        try:
            graph = gfut.result(timeout=80)
        except Exception as e:  # noqa: BLE001
            graph = {"error": str(e)[:200]}
    ctx = [{k: c.get(k) for k in ("disruption_id", "text")} for c in sres["results"]]
    if graph and graph.get("answer"):  # Synapt's graph-RAG answer is the response
        answer, method = graph["answer"], "synapt"
    else:  # extractive fallback when Synapt is off or failed
        answer, method = ("Most relevant historical cases:\n\n" +
                          "\n".join(f"- **{c['disruption_id']}** — {c['text']}" for c in ctx[:5])), "extractive"
    return {"question": q["text"], "answer": answer, "method": method, "sources": sres["results"],
            "semantic_source": sres["semantic_source"], "fallback_reason": sres["fallback_reason"], "graph": graph}


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
