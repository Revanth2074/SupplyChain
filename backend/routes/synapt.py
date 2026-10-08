"""
Synapt Context Substrate API Routes.
Connectivity, provider stats, graph-RAG explorer, procedures (playbooks), episodic memory,
ticket-store labelling, fixed provider-scoped graph analytics, and Synapt's own quality signals.
"""

import time
from typing import Any

from fastapi import APIRouter, HTTPException

from agents import synapt_tools as syn
from agents.classifier import classify
from agents.guardrails import validate_text
from agents.planner import strategy_table
from agents.prediction import registry
from agents.retrieval import synapt_label
from agents.state import describe
from config import settings
from schemas import GraphRequest, LabelRequest, compact
from services import feedback
from services.bootstrap import ready

router = APIRouter(prefix="/synapt", tags=["Synapt Context Substrate"])


@router.get("/ping")
def synapt_ping():
    t0 = time.time()
    try:
        s = syn.stats()
        return {"ok": True, "latency_ms": int((time.time() - t0) * 1000), "stats": s}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "latency_ms": int((time.time() - t0) * 1000)}


@router.get("/knowledge")
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


@router.get("/insights/{key}")
def synapt_insight(key: str):
    """Provider-scoped read-only graph query from a fixed template (no free-form Cypher)."""
    if key not in syn.GRAPH_INSIGHTS:
        raise HTTPException(404, f"unknown insight; choose one of {list(syn.GRAPH_INSIGHTS)}")
    try:
        return syn.graph_insight(key)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Synapt graph query failed: {e}") from e


@router.post("/graph")
def synapt_graph(req: GraphRequest):
    """Graph-RAG answer with the reasoning subgraph Synapt traversed (for the graph explorer)."""
    q = validate_text(req.question, "question")
    try:
        return syn.fetch_synapt_rag(q["text"], req.top_k, req.hops, 90, "explorer")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Synapt query failed: {e}") from e


@router.get("/procedures")
def synapt_procedures(query: str = "disruption response playbook"):
    validate_text(query, "query", require_domain=False)
    try:
        return {"procedures": syn.fetch_synapt_procedures(query)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Synapt procedures failed: {e}") from e


@router.get("/episodes")
def synapt_episodes(query: str = "", top_k: int = 5):
    if query:
        validate_text(query, "query", require_domain=False)
    try:
        return syn.episodes(query, max(1, min(top_k, 20)))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Synapt episodes failed: {e}") from e


@router.post("/label")
def synapt_label_ep(req: LabelRequest):
    """Synapt-native labelling (ticket store if present, else Synapt semantic kNN) compared
    with the app's classifier and the ML/statistics strategy recommendation."""
    ready()
    v = validate_text(req.description, "description")
    cls = classify(v["text"])
    inc = {**cls["fields"], **(compact(req.incident) or {})}
    synapt_out: dict[str, Any]
    try:
        # semantic nearest-case vote covers every field; the ticket store (if any) adds its own labels
        synapt_out = synapt_label(f"{v['text']} {describe(inc)}")
        synapt_out["note"] = "Labels vote over the nearest Synapt-retrieved historical cases."
        if (syn.stats() or {}).get("has_ticket_store"):
            try:
                tl = syn.label_ticket({"title": describe(inc), "description": v["text"]})
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
    strat = strategy_table(inc)["strategies"] if inc.get("disruption_type") else []
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


@router.get("/quality")
def synapt_quality():
    """Synapt's own confidence / trust signals for every graph query the app has made."""
    return feedback.synapt_quality()
