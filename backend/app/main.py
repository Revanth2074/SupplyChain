"""FastAPI microservice: AI-Powered Supply Chain Disruption Assistant (Synapt)."""
from __future__ import annotations

import concurrent.futures as cf
import json
import logging
import threading
import time
from typing import Any, Literal, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import (agents, analysis, decision, evaluation, fallback_lab, faults, feedback, llm, network, ops, portfolio,
               risk_watch, webapp)
from . import synapt_service as syn
from .config import settings
from .data_store import store
from .guardrails import validate_incident, validate_text
from .judge import judge
from .ml_models import registry
from .retrieval import hybrid_search, synapt_label

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")

app = FastAPI(title="Supply Chain Disruption Assistant", version="1.0.0",
              description="Synapt-powered hybrid RAG, multi-agent analysis, prediction & evaluation.")
webapp.install(app)  # password gate (APP_PASSWORD) + CORS (CORS_ORIGINS)
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
    ops.init()
    risk_watch.init()
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
    supplier_tier: Optional[int] = Field(None, ge=1, le=4)
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


class PortfolioReq(BaseModel):
    suppliers: Optional[list[dict[str, Any]]] = Field(None, max_length=500)
    csv: Optional[str] = Field(None, max_length=500_000)
    severity: int = Field(3, ge=1, le=5)


class GraphReq(BaseModel):
    question: str
    hops: Optional[int] = Field(None, ge=0, le=4)
    top_k: int = Field(5, ge=1, le=20)


class LabelReq(BaseModel):
    description: str
    incident: Optional[Incident] = None


class DecisionReq(BaseModel):
    incident: Incident
    costs: Optional[dict[str, dict[str, float]]] = None


class PortfolioCsvReq(BaseModel):
    csv: Optional[str] = Field(None, max_length=500_000)
    severity: int = Field(3, ge=1, le=5)


class OfflineReq(PortfolioCsvReq):
    supplier: str
    disruption_type: Optional[str] = None


class SignalReq(BaseModel):
    headline: str = Field(..., min_length=8, max_length=300)
    detail: Optional[str] = Field("", max_length=2000)
    send_to_synapt: bool = False


class SignalPatch(BaseModel):
    active: bool


class IncidentReq(BaseModel):
    analysis_id: str


class IncidentPatch(BaseModel):
    status: Optional[str] = None
    owner: Optional[str] = Field(None, max_length=80)


class ActionReq(BaseModel):
    title: str = Field(..., min_length=3, max_length=300)
    owner: str = Field("Operations", max_length=80)
    due_hours: float = Field(24, gt=0, le=24 * 90)


class ActionPatch(BaseModel):
    status: Optional[str] = None
    actual_recovery_days: Optional[float] = Field(None, ge=0, le=1000)
    actual_loss_usd: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = Field(None, max_length=500)


class SwitchReq(BaseModel):
    enabled: bool
    minutes: float = Field(30, ge=1, le=faults.MAX_MINUTES)


class SelfTestReq(BaseModel):
    full_workflow: bool = True


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
                       "trained_at": registry.meta.get("trained_at"), "fallback": registry.fallback()},
            "simulated_outages": faults.active_list()}


@app.get("/api/synapt/ping")
def synapt_ping():
    t0 = time.time()
    try:
        s = syn.stats()
        return {"ok": True, "latency_ms": int((time.time() - t0) * 1000), "stats": s}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "latency_ms": int((time.time() - t0) * 1000)}


@app.get("/api/synapt/knowledge")
def synapt_knowledge():
    """What the Synapt provider holds (stats), whether it has a ticket store, and episodic memory."""
    out: dict[str, Any] = {"provider_id": settings.SYNAPT_PROVIDER_ID}
    for key, fn in (("stats", syn.stats), ("episodes", lambda: syn.episodes())):
        try:
            out[key] = fn()
        except Exception as e:  # noqa: BLE001
            out[key] = {"error": str(e)[:200]}
    out["has_ticket_store"] = bool((out.get("stats") or {}).get("has_ticket_store"))
    out["insights"] = [{"key": k, "title": t, "description": d} for k, (t, d, _) in syn.GRAPH_INSIGHTS.items()]
    return out


@app.get("/api/synapt/insights/{key}")
def synapt_insight(key: str):
    """Provider-scoped read-only graph query from a fixed template (no free-form Cypher)."""
    if key not in syn.GRAPH_INSIGHTS:
        raise HTTPException(404, f"unknown insight; choose one of {list(syn.GRAPH_INSIGHTS)}")
    try:
        return syn.graph_insight(key)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Synapt graph query failed: {e}") from e


@app.post("/api/synapt/graph")
def synapt_graph(req: GraphReq):
    """Graph-RAG answer with the reasoning subgraph Synapt traversed (for the graph explorer)."""
    q = validate_text(req.question, "question")
    try:
        return syn.graph_query(q["text"], req.top_k, req.hops, 90, "explorer")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Synapt query failed: {e}") from e


@app.get("/api/synapt/procedures")
def synapt_procedures(query: str = "disruption response playbook"):
    validate_text(query, "query", require_domain=False)
    try:
        return {"procedures": syn.procedures(query)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Synapt procedures failed: {e}") from e


@app.get("/api/synapt/episodes")
def synapt_episodes(query: str = "", top_k: int = 5):
    if query:
        validate_text(query, "query", require_domain=False)
    try:
        return syn.episodes(query, max(1, min(top_k, 20)))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Synapt episodes failed: {e}") from e


@app.post("/api/synapt/label")
def synapt_label_ep(req: LabelReq):
    """Synapt-native labelling (ticket store if present, else Synapt semantic kNN) compared
    with the app's classifier and the ML/statistics strategy recommendation."""
    _ready()
    v = validate_text(req.description, "description")
    cls = analysis.classify(v["text"])
    inc = {**cls["fields"], **(_f(req.incident) or {})}
    synapt_out: dict[str, Any]
    try:
        # semantic nearest-case vote covers every field; the ticket store (if any) adds its own labels
        synapt_out = synapt_label(f"{v['text']} {agents._describe(inc)}")
        synapt_out["note"] = "Labels vote over the nearest Synapt-retrieved historical cases."
        if (syn.stats() or {}).get("has_ticket_store"):
            try:
                tl = syn.label_ticket({"title": agents._describe(inc), "description": v["text"]})
                for f, d in tl["fields"].items():
                    synapt_out["fields"][f] = d["labels"]
                synapt_out["ticket_store"] = {"fields": list(tl["fields"]), "neighbours": tl["neighbours"],
                                              "reliability": {f: d["reliability"] for f, d in tl["fields"].items()}}
                synapt_out["method"] = "ticket-store + semantic kNN"
                synapt_out["note"] = ("recovery_outcome comes from the Synapt ticket store "
                                      "(trident_label_ticket); other fields vote over the nearest cases.")
            except Exception as e:  # noqa: BLE001
                synapt_out["ticket_store_error"] = str(e)[:200]
    except Exception as e:  # noqa: BLE001
        synapt_out = {"method": "unavailable", "error": str(e)[:200], "fields": {}}
    strat = analysis.strategy_table(inc)["strategies"] if inc.get("disruption_type") else []
    best = strat[0]["strategy"] if strat else None
    app_view = {**{k: inc.get(k) for k in ("disruption_type", "industry", "supplier_region")}, "response_type": best}
    if inc.get("disruption_type"):
        days = registry.predict({**inc, **({"response_type": best} if best else {})})["full_recovery_days"]
        app_view["recovery_outcome"] = ("Fast" if days <= 30 else "Normal" if days <= 60 else
                                        "Slow" if days <= 120 else "Very Slow")
        app_view["predicted_full_recovery_days"] = days
    agree = {}
    for f, cands in (synapt_out.get("fields") or {}).items():
        if cands and app_view.get(f):
            agree[f] = cands[0]["value"] == app_view[f]
    return {"synapt": synapt_out, "app": {"classification": cls, "recommended_strategy": app_view["response_type"],
                                          "fields": app_view}, "agreement": agree}


@app.get("/api/synapt/quality")
def synapt_quality():
    """Synapt's own confidence / trust signals for every graph query the app has made."""
    return feedback.synapt_quality()


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
    gfut = _pool.submit(syn.graph_query, q["text"], req.top_k, None, 75, "ask") if (req.use_graph and syn.configured()) else None
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


@app.post("/api/whatif")
def whatif(inc: Incident):
    """Counterfactual analysis: how outcomes change if one lever (backup, response speed, tier,
    strategy) had been different."""
    _ready()
    d = {k: v for k, v in inc.model_dump().items() if v is not None}
    validate_incident(d, store.options())
    if not d.get("disruption_type"):
        raise HTTPException(422, "disruption_type is required")
    return {"incident": d, **registry.whatif(d)}


@app.get("/api/portfolio/sample", response_class=PlainTextResponse)
def portfolio_sample():
    return portfolio.sample_csv()


@app.post("/api/portfolio")
def portfolio_score(req: PortfolioReq):
    """Score a supplier portfolio across all disruption types -> heatmap + ranked risk list."""
    _ready()
    try:
        rows = portfolio.parse_csv(req.csv) if req.csv else (req.suppliers or [])
        return portfolio.score(rows, req.severity)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


# ------------------------------------------------------------------ decision support
def _incident_dict(inc: Incident) -> dict:
    d = {k: v for k, v in inc.model_dump().items() if v is not None}
    validate_incident(d, store.options())
    if not d.get("disruption_type"):
        raise HTTPException(422, "disruption_type is required")
    return d


@app.post("/api/decision")
def decision_ep(req: DecisionReq):
    """Compare response scenarios: predicted loss and recovery vs mitigation cost (ROI)."""
    _ready()
    return decision.compare_scenarios(_incident_dict(req.incident), req.costs)


@app.post("/api/rootcause")
def rootcause_ep(inc: Incident):
    """How the disruption propagates (cause -> effects) and which factors made it worse or better."""
    _ready()
    return decision.root_cause(_incident_dict(inc))


@app.post("/api/rootcause/synapt")
def rootcause_synapt(inc: Incident):
    """Ask the Synapt knowledge graph to explain the causal chain, with its evidence subgraph."""
    d = _incident_dict(inc)
    q = (f"For a {d['disruption_type']} disruption at a Tier {d.get('supplier_tier', 2)} {d.get('industry', '')} supplier"
         f"{' with no backup supplier' if d.get('has_backup_supplier') is False else ''}, what drives the production impact "
         f"and recovery time, and which response strategy recovers fastest?")
    try:
        return syn.graph_query(q, 6, None, 90, "rootcause")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Synapt query failed: {e}") from e


def _scored(csv: Optional[str], severity: int = 3) -> dict:
    try:
        return portfolio.score(portfolio.rows_or_sample(csv), severity)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.post("/api/early-warning")
def early_warning_ep(req: PortfolioCsvReq):
    """Forward-looking supplier risk: external signals + operational health + ML impact-if-disrupted."""
    _ready()
    scored = _scored(req.csv, req.severity)
    sigs = risk_watch.list_signals(active_only=True)
    return {**risk_watch.early_warning(scored, sigs), "signals": risk_watch.signal_impacts(scored, sigs)}


@app.get("/api/signals")
def signals_ep():
    return risk_watch.list_signals()


@app.post("/api/signals")
def add_signal(req: SignalReq):
    _ready()
    try:
        return risk_watch.add_manual(req.headline, req.detail or "", req.send_to_synapt)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.patch("/api/signals/{sid}")
def patch_signal(sid: str, req: SignalPatch):
    risk_watch.set_active(sid, req.active)
    return {"id": sid, "active": req.active}


@app.post("/api/signals/{sid}/synapt")
def signal_to_synapt(sid: str):
    try:
        return risk_watch.push_to_synapt(sid)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/api/signals/fetch-live")
def fetch_live_signals():
    """Pull current orange/red alerts from the public GDACS disaster feed."""
    try:
        return risk_watch.fetch_gdacs()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Live feed unavailable: {e}") from e


@app.post("/api/network")
def network_ep(req: PortfolioCsvReq):
    _ready()
    return network.build(_scored(req.csv, req.severity))


@app.post("/api/network/offline")
def network_offline(req: OfflineReq):
    _ready()
    try:
        return network.offline(_scored(req.csv, req.severity), req.supplier, req.disruption_type)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


# ------------------------------------------------------------------ incident desk
@app.get("/api/incidents")
def incidents_ep():
    return ops.list_incidents()


@app.post("/api/incidents")
def open_incident(req: IncidentReq):
    a = feedback.get_analysis(req.analysis_id)
    if not a:
        raise HTTPException(404, "analysis not found")
    return {"id": ops.create_from_analysis(a)}


@app.post("/api/incidents/seed-demo")
def seed_incidents():
    _ready()
    return {"created": ops.seed_demo()}


@app.patch("/api/incidents/{iid}")
def patch_incident(iid: str, req: IncidentPatch):
    try:
        ops.update_incident(iid, req.status, req.owner)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"id": iid}


@app.post("/api/incidents/{iid}/actions")
def add_incident_action(iid: str, req: ActionReq):
    try:
        return {"id": ops.add_action(iid, req.title, req.owner, req.due_hours)}
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@app.patch("/api/actions/{aid}")
def patch_action(aid: str, req: ActionPatch):
    try:
        return ops.update_action(aid, req.status, req.actual_recovery_days, req.actual_loss_usd, req.notes)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.get("/api/overview")
def overview():
    """One-screen status for the home page: what the assistant watches and what needs attention."""
    _ready()
    scored = _scored(None)
    sigs = risk_watch.list_signals(active_only=True)
    ew = risk_watch.early_warning(scored, sigs)
    incs = ops.list_incidents()
    open_incs = [i for i in incs if i["status"] != "resolved"]
    fb = feedback.stats()
    q = feedback.synapt_quality()
    return {
        "cases": int(len(store.df)), "suppliers": scored["count"], "signals_active": len(sigs),
        "early_warning": ew["levels"], "top_risks": ew["suppliers"][:3],
        "incidents_open": len(open_incs), "sla_breached": sum(i["breached"] for i in open_incs),
        "escalated": sum(i["escalated"] for i in open_incs),
        "actions_open": sum(1 for i in open_incs for a in i["actions"] if a["status"] not in ("done", "rejected")),
        "feedback": {"total": fb["total"], "with_outcomes": fb["with_outcomes"], "avg_rating": fb["avg_rating"]},
        "synapt": {**syn.status(), "answers": q["n"], "avg_confidence": q["summary"].get("confidence")},
        "models": {k: v.get("r2") for k, v in registry.meta.get("targets", {}).items() if "r2" in v},
    }


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


# must stay last: serves the built UI and falls back to index.html for client-side routes
# ------------------------------------------------------------------ fallback lab
@app.get("/api/fallback-lab")
def fallback_lab_status():
    """Outage switches (with what fails and what takes over) and the current Synapt breaker state."""
    return {**faults.status(), "synapt": syn.status(), "llm_configured": llm.available(),
            "models_fallback": registry.fallback()}


@app.put("/api/fallback-lab/{name}")
def fallback_lab_switch(name: str, req: SwitchReq):
    """Simulate an outage of one dependency (enabled=true) or restore it. Restores itself after `minutes`."""
    try:
        faults.set_switch(name, req.enabled, req.minutes)
    except KeyError as e:
        raise HTTPException(404, f"Unknown switch '{name}'. Options: {list(faults.SWITCHES)}") from e
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    return fallback_lab_status()


@app.post("/api/fallback-lab/reset")
def fallback_lab_reset():
    faults.reset()
    return fallback_lab_status()


@app.post("/api/fallback-lab/selftest")
def fallback_lab_selftest(req: SelfTestReq):
    """Run every feature once; each check passes when it answered via the expected engine."""
    _ready()
    return fallback_lab.run(req.full_workflow)


webapp.serve_frontend(app)
