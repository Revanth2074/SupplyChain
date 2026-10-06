"""FastAPI microservice: AI-Powered Supply Chain Disruption Assistant (Synapt)."""
from __future__ import annotations

import concurrent.futures as cf
import json
import logging
import threading
import time
from typing import Any, Literal, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import agents, analysis, evaluation, feedback, llm
from . import synapt_service as syn
from .config import settings
from .data_store import store
from .guardrails import validate_incident, validate_text
from .judge import judge
from .ml_models import registry
from .retrieval import hybrid_search

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")

app = FastAPI(title="Supply Chain Disruption Assistant", version="1.0.0",
              description="Synapt-powered hybrid RAG, multi-agent analysis, prediction & evaluation.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_pool = cf.ThreadPoolExecutor(max_workers=4)
_boot = {"stage": "starting", "error": None}


def _bootstrap():
    try:
        _boot["stage"] = "loading data"
        store.load()
        feedback.init()
        _boot["stage"] = "loading/training models"
        registry.load_or_train()
        _boot["stage"] = "ready"
    except Exception as e:  # noqa: BLE001
        log.exception("bootstrap failed")
        _boot.update(stage="error", error=str(e))


@app.on_event("startup")
def startup():
    feedback.init()
    threading.Thread(target=_bootstrap, daemon=True).start()


def _ready():
    if _boot["stage"] != "ready":
        raise HTTPException(503, f"Service warming up: {_boot['stage']}")


# ------------------------------------------------------------------ schemas
class Filters(BaseModel):
    disruption_type: Optional[list[str]] = None
    industry: Optional[list[str]] = None
    supplier_tier: Optional[list[int]] = None
    supplier_region: Optional[list[str]] = None
    supplier_size: Optional[list[str]] = None
    response_type: Optional[list[str]] = None
    disruption_severity: Optional[list[int]] = None
    severity_min: Optional[int] = Field(None, ge=1, le=5)
    severity_max: Optional[int] = Field(None, ge=1, le=5)
    has_backup_supplier: Optional[bool] = None


class Incident(BaseModel):
    disruption_type: Optional[str] = None
    industry: Optional[str] = None
    supplier_tier: Optional[int] = Field(None, ge=1, le=3)
    supplier_region: Optional[str] = None
    supplier_size: Optional[str] = None
    has_backup_supplier: Optional[bool] = None
    disruption_severity: Optional[int] = Field(None, ge=1, le=5)
    response_type: Optional[str] = None
    response_time_days: Optional[int] = Field(None, ge=0, le=365)
    production_impact_pct: Optional[float] = Field(None, ge=0, le=100)
    revenue_loss_usd: Optional[float] = Field(None, ge=0)
    label: Optional[str] = None


class SearchReq(BaseModel):
    query: str
    filters: Optional[Filters] = None
    top_k: int = Field(10, ge=1, le=50)
    mode: Literal["hybrid", "semantic", "keyword"] = "hybrid"
    alpha: float = Field(0.6, ge=0, le=1)


class ClassifyReq(BaseModel):
    description: str


class AnalyzeReq(BaseModel):
    description: Optional[str] = None
    incident: Optional[Incident] = None
    filters: Optional[Filters] = None
    top_k: int = Field(8, ge=3, le=20)
    use_graph: bool = True
    judge: bool = True


class PrioritizeReq(BaseModel):
    incidents: list[Incident] = Field(..., min_length=1, max_length=200)


class AskReq(BaseModel):
    question: str
    filters: Optional[Filters] = None
    top_k: int = Field(6, ge=1, le=20)
    use_graph: bool = True


class JudgeReq(BaseModel):
    report: str
    incident: Optional[Incident] = None
    case_ids: list[str] = []


class FeedbackReq(BaseModel):
    analysis_id: Optional[str] = None
    rating: int = Field(..., ge=1, le=5)
    helpful: Optional[bool] = None
    chosen_strategy: Optional[str] = None
    comment: Optional[str] = Field(None, max_length=1000)
    actual_production_impact_pct: Optional[float] = Field(None, ge=0, le=100)
    actual_revenue_loss_usd: Optional[float] = Field(None, ge=0)
    actual_full_recovery_days: Optional[float] = Field(None, ge=0, le=1000)
    actual_partial_recovery_days: Optional[float] = Field(None, ge=0, le=1000)


class EvalReq(BaseModel):
    limit: Optional[int] = Field(None, ge=1, le=20)
    use_graph: bool = False
    include_feedback: bool = True


def _f(m: Optional[BaseModel]) -> dict | None:
    if not m:
        return None
    d = {k: v for k, v in m.model_dump().items() if v not in (None, [], "")}
    return d or None


# ------------------------------------------------------------------ system
@app.get("/api/health")
def health():
    return {"status": _boot["stage"], "error": _boot["error"], "synapt": syn.status(),
            "llm": {"configured": llm.available(), "base_url": settings.LLM_BASE_URL, "model": settings.LLM_MODEL,
                    "judge_model": settings.JUDGE_MODEL},
            "data": {"ready": store.ready, "rows": int(len(store.df)) if store.df is not None else 0},
            "models": {"ready": registry.ready, "training": registry.training,
                       "trained_at": registry.meta.get("trained_at")}}


@app.get("/api/synapt/ping")
def synapt_ping():
    t0 = time.time()
    try:
        s = syn.stats()
        return {"ok": True, "latency_ms": int((time.time() - t0) * 1000), "stats": s}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "latency_ms": int((time.time() - t0) * 1000)}


@app.get("/api/meta")
def meta():
    _ready()
    return {"options": store.options(), "agents": [{"id": a, "name": n, "description": d} for a, n, d in agents.AGENTS]}


# ------------------------------------------------------------------ Req 1: core
@app.post("/api/search")
def search(req: SearchReq):
    _ready()
    q = validate_text(req.query, "query")
    filters = _f(req.filters)
    res = hybrid_search(q["text"], filters, req.top_k, req.mode, alpha=req.alpha)
    res["warnings"] = q["warnings"]
    return res


@app.post("/api/classify")
def classify(req: ClassifyReq):
    _ready()
    v = validate_text(req.description, "description")
    res = analysis.classify(v["text"])
    res["warnings"] = v["warnings"]
    return res


@app.post("/api/recommend")
def recommend(req: AnalyzeReq):
    """Lightweight recommendation (no multi-agent) based on historical strategy effectiveness."""
    _ready()
    inc = _resolve_incident(req.description, req.incident)
    strat = analysis.strategy_table(inc)
    sim = hybrid_search(req.description or agents._describe(inc), _f(req.filters), req.top_k, reference=inc)
    top = strat["strategies"][0] if strat["strategies"] else None
    return {"incident": inc, "recommended_strategy": top, "alternatives": strat["strategies"][1:3],
            "cohort": strat["scope"], "cohort_size": strat["n"], "similar_cases": sim["results"],
            "semantic_source": sim["semantic_source"]}


@app.post("/api/prioritize")
def prioritize(req: PrioritizeReq):
    _ready()
    opts = store.options()
    out = []
    for i, inc in enumerate(req.incidents):
        d = {k: v for k, v in inc.model_dump().items() if v is not None}
        validate_incident(d, opts)
        pred = registry.predict(d)
        p = analysis.priority(d, pred)
        out.append({"index": i, "label": d.get("label") or f"Incident {i + 1}", "incident": d, "priority": p,
                    "prediction": {k: pred[k] for k in ("production_impact_pct", "revenue_loss_usd",
                                                        "full_recovery_days", "risk_level", "risk_probability")}})
    out.sort(key=lambda r: -r["priority"]["score"])
    for rank, r in enumerate(out, 1):
        r["rank"] = rank
    return {"count": len(out), "ranked": out}


@app.post("/api/ask")
def ask(req: AskReq):
    """RAG Q&A: Synapt graph-RAG + hybrid retrieval, synthesised by the LLM."""
    _ready()
    q = validate_text(req.question, "question")
    filters = _f(req.filters)
    gfut = _pool.submit(syn.graph_query, q["text"], req.top_k, None, 75) if (req.use_graph and syn.configured()) else None
    sres = hybrid_search(q["text"], filters, req.top_k)
    graph = None
    if gfut:
        try:
            graph = gfut.result(timeout=80)
        except Exception as e:  # noqa: BLE001
            graph = {"error": str(e)[:200]}
    ctx = [{k: c.get(k) for k in ("disruption_id", "text")} for c in sres["results"]]
    answer, method = None, "llm"
    try:
        if not llm.available():
            raise RuntimeError("LLM unavailable")
        sysmsg = ("You are a supply-chain disruption analyst. Answer the question using ONLY the context "
                  "(historical cases and the Synapt knowledge-graph answer). Cite case IDs. Be concise, use Markdown "
                  "bullets, and state if evidence is insufficient.")
        answer = llm.chat([{"role": "system", "content": sysmsg},
                           {"role": "user", "content": json.dumps({"question": q["text"], "cases": ctx,
                                                                    "synapt_answer": (graph or {}).get("answer")})}],
                          temperature=0.2, max_tokens=900)
    except Exception as e:  # noqa: BLE001
        method = "synapt" if graph and graph.get("answer") else "extractive"
        answer = (graph or {}).get("answer") or ("Most relevant historical cases:\n\n" +
                                                 "\n".join(f"- **{c['disruption_id']}** — {c['text']}" for c in ctx[:5]))
        log.info("ask fallback: %s", e)
    return {"question": q["text"], "answer": answer, "method": method, "sources": sres["results"],
            "semantic_source": sres["semantic_source"], "fallback_reason": sres["fallback_reason"], "graph": graph}


def _resolve_incident(description: Optional[str], incident: Optional[Incident]) -> dict:
    given = {k: v for k, v in (incident.model_dump() if incident else {}).items() if v not in (None, "")}
    validate_incident(given, store.options())
    if description:
        v = validate_text(description, "description")
        cls = analysis.classify(v["text"])
        given = {**cls["fields"], **given}
    if not given.get("disruption_type"):
        raise HTTPException(422, "Could not determine disruption_type; provide it or a richer description")
    return given


# ------------------------------------------------------------------ Req 2: advanced
@app.post("/api/predict")
def predict(inc: Incident):
    _ready()
    d = {k: v for k, v in inc.model_dump().items() if v is not None}
    validate_incident(d, store.options())
    pred = registry.predict(d)
    return {"incident": d, "prediction": pred, "priority": analysis.priority(d, pred)}


@app.post("/api/explain")
def explain(inc: Incident):
    _ready()
    d = {k: v for k, v in inc.model_dump().items() if v is not None}
    validate_incident(d, store.options())
    return {"incident": d, "explanation": registry.explain(d)}


@app.get("/api/models")
def models_info():
    _ready()
    return registry.meta


@app.post("/api/models/retrain")
def retrain(bg: BackgroundTasks):
    _ready()
    extra = feedback.outcome_rows()
    if registry.training:
        return {"status": "already training"}
    bg.add_task(registry.train, extra)
    return {"status": "retraining started", "feedback_rows": int(len(extra))}


@app.get("/api/insights")
def insights():
    _ready()
    return analysis.insights()


@app.post("/api/analyze")
def analyze(req: AnalyzeReq):
    _ready()
    payload = req.model_dump()
    payload["incident"] = _f(req.incident)
    payload["filters"] = _f(req.filters)
    try:
        return agents.run_sync(payload)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.post("/api/analyze/stream")
def analyze_stream(req: AnalyzeReq):
    """Server-Sent Events stream of the multi-agent workflow."""
    _ready()
    payload = req.model_dump()
    payload["incident"] = _f(req.incident)
    payload["filters"] = _f(req.filters)

    def gen():
        try:
            for ev in agents.run_workflow(payload):
                yield f"data: {json.dumps(ev, default=str)}\n\n"
        except HTTPException as e:
            yield f"data: {json.dumps({'type': 'error', 'error': e.detail})}\n\n"
        except Exception as e:  # noqa: BLE001
            log.exception("workflow failed")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/analyses")
def analyses(limit: int = 20):
    return feedback.recent_analyses(limit)


@app.get("/api/analyses/{aid}")
def get_analysis(aid: str):
    a = feedback.get_analysis(aid)
    if not a:
        raise HTTPException(404, "analysis not found")
    return a


@app.post("/api/judge")
def judge_ep(req: JudgeReq):
    _ready()
    validate_text(req.report, "report", require_domain=False)
    cases = [c for c in (store.get_case(i) for i in req.case_ids) if c]
    inc = _f(req.incident) or {}
    pred = registry.predict(inc) if inc.get("disruption_type") else None
    strat = analysis.strategy_table(inc)["strategies"] if inc.get("disruption_type") else []
    return judge(req.report, {"incident": inc, "cases": cases, "strategies": strat, "prediction": pred})


@app.post("/api/feedback")
def add_feedback(req: FeedbackReq):
    d = req.model_dump()
    if req.comment:
        d["comment"] = validate_text(req.comment, "comment", require_domain=False)["text"]
    a = feedback.get_analysis(req.analysis_id) if req.analysis_id else None
    if a:
        d["disruption_type"] = a["incident"].get("disruption_type")
        d["industry"] = a["incident"].get("industry")
        d["recommended_strategy"] = (a["report"].get("plan") or {}).get("primary_strategy")
        qid = a.get("synapt_query_id")
        if qid:
            try:
                verdict = "deflected" if req.rating >= 4 else "partial" if req.rating == 3 else "not_deflected"
                syn.send_feedback(qid, verdict, req.rating / 5, req.comment)
                d["synapt_sent"] = True
            except Exception as e:  # noqa: BLE001
                log.warning("Synapt feedback failed: %s", e)
    fid = feedback.add_feedback(d)
    analysis.insights.cache_clear()
    return {"id": fid, "synapt_sent": bool(d.get("synapt_sent")), "boosts": feedback.strategy_boosts().__len__()}


@app.get("/api/feedback/stats")
def feedback_stats():
    return feedback.stats()


@app.post("/api/evaluate")
def run_eval(req: EvalReq):
    _ready()
    return evaluation.start(req.limit, req.use_graph, req.include_feedback)


@app.get("/api/evaluate/status")
def eval_status():
    return evaluation.status()


@app.get("/api/evaluate/results")
def eval_results():
    r = evaluation.results()
    if not r:
        raise HTTPException(404, "No evaluation results yet")
    return r
