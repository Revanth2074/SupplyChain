"""
Hybrid Retrieval Engine & Reciprocal Rank Fusion (RRF) Node.
Fuses lexical BM25 candidates from the local 100k-case index with Synapt Context Substrate
semantic retrieval (trident_get_chunks, joined back to the CSV) and an attribute-profile leg over
all 100k rows; trident_search adds knowledge-graph nodes (playbook procedures and steps).
Falls back to the local LSA semantic index when Synapt is unavailable.
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
import time

import numpy as np

from agents import synapt_tools as syn
from services.data_store import store

log = logging.getLogger("retrieval")
RRF_K = 60
_pool = cf.ThreadPoolExecutor(max_workers=4)


def filters_to_text(f: dict | None) -> str:
    if not f:
        return ""
    parts = []
    for k, label in (("disruption_type", "Disruption type"), ("industry", "Industry"),
                     ("supplier_region", "Supplier region"), ("supplier_size", "Supplier size"),
                     ("response_type", "Response strategy")):
        v = f.get(k)
        if v:
            parts.append(f"{label}: {', '.join(v) if isinstance(v, list) else v}.")
    if f.get("supplier_tier"):
        t = f["supplier_tier"] if isinstance(f["supplier_tier"], list) else [f["supplier_tier"]]
        parts.append("Supplier tier: " + ", ".join(f"Tier {x}" for x in t) + ".")
    if f.get("disruption_severity"):
        s = f["disruption_severity"] if isinstance(f["disruption_severity"], list) else [f["disruption_severity"]]
        parts.append("Severity was " + "/".join(map(str, s)) + " out of 5.")
    elif f.get("severity_min"):
        parts.append(f"Severity at least {f['severity_min']} out of 5.")
    if f.get("has_backup_supplier") is not None:
        parts.append("The supplier had a backup supplier." if f["has_backup_supplier"] else
                     "The supplier had no backup supplier.")
    return " ".join(parts)


def _matches(case: dict, f: dict | None) -> bool:
    if not f:
        return True
    import pandas as pd
    return not store.apply_filters(pd.DataFrame([case]), f).empty


SIM_WEIGHTS = {"disruption_type": 3, "industry": 2, "supplier_tier": 1, "supplier_region": 1,
               "supplier_size": 1, "has_backup_supplier": 1.5, "disruption_severity": 2}


def similarity(case: dict, ref: dict | None) -> float | None:
    """Attribute-level similarity (0-1) between a case and the reference incident."""
    if not ref:
        return None
    tot = got = 0.0
    for k, wt in SIM_WEIGHTS.items():
        if ref.get(k) is None or ref.get(k) == "":
            continue
        tot += wt
        if k == "disruption_severity":
            got += wt * max(0, 1 - abs(int(case[k]) - int(ref[k])) / 4)
        elif k == "supplier_tier":
            got += wt * (1 if int(case[k]) == int(ref[k]) else 0)
        else:
            got += wt * (1 if case[k] == ref[k] else 0)
    return round(got / tot, 3) if tot else None


def profile_matches(ref: dict, filters: dict | None, k: int) -> list[tuple[str, float]]:
    """Structured leg: the cases in the full 100k CSV whose attributes best match the incident
    (same weights as `similarity`, vectorised). Synapt only holds a 4k-case sample, so without
    this leg exact-profile precedents are mostly missed."""
    df = store.apply_filters(store.df, filters) if filters else store.df
    score = np.zeros(len(df))
    tot = 0.0
    for col, wt in SIM_WEIGHTS.items():
        v = ref.get(col)
        if v is None or v == "":
            continue
        tot += wt
        if col == "disruption_severity":
            score += wt * np.clip(1 - np.abs(df[col].to_numpy() - int(v)) / 4, 0, None)
        elif col == "supplier_tier":
            score += wt * (df[col].to_numpy() == int(v))
        elif col == "has_backup_supplier":
            score += wt * (df[col].to_numpy() == bool(v))
        else:
            score += wt * (df[col].to_numpy() == v)
    if not tot:
        return []
    score /= tot
    top = np.argsort(-score, kind="stable")[:k]
    ids = df["disruption_id"].to_numpy()
    return [(ids[i], float(score[i])) for i in top]


def lexical_search(query: str, filters: dict | None, top_k: int) -> list[tuple[str, float]]:
    """Keyword leg: BM25 over the local case index (exact words, part names, tiers)."""
    return store.keyword_search(query, filters, top_k)


def semantic_search_synapt(query: str, filters: dict | None, top_k: int, pool_k: int | None = None) -> dict:
    """Semantic leg via the Synapt Context Substrate: trident_get_chunks (case documents, joined back to
    the CSV by DIS- id) with the local LSA index as fallback, plus trident_search (knowledge-graph nodes:
    playbook procedures and steps) returned as supporting knowledge."""
    hits: list[tuple[str, float]] = []
    texts: dict[str, str] = {}
    source, fallback_reason = "synapt", None
    node_fut = _pool.submit(syn.search_nodes, query, 5) if syn.configured() else None
    try:
        seen = set()
        for h in syn.get_chunks(query, top_k=max(8, min(top_k, 20))):
            cid = h.get("id")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            c = store.get_case(cid)
            if c and h.get("masked_region"):
                syn.regions.learn(h["masked_region"], c["supplier_region"])
            if c and _matches(c, filters):
                hits.append((cid, 1.0 / (1 + h["rank"])))
                texts[cid] = h["text"]
        if not hits:
            # Synapt answered but nothing passed filters -> supplement with local semantic
            fallback_reason = "Synapt returned no cases matching filters; supplemented with local semantic index"
            hits = store.semantic_search(query, filters, pool_k or top_k)
            source = "synapt+local"
    except Exception as e:  # noqa: BLE001
        log.warning("Synapt semantic leg failed -> local fallback: %s", e)
        fallback_reason = str(e)
        source = "local-lsa"
        hits = store.semantic_search(query, filters, pool_k or top_k)
    nodes = []
    if node_fut:
        try:
            nodes = node_fut.result(timeout=30)
        except Exception as e:  # noqa: BLE001
            log.info("trident_search leg skipped: %s", e)
    return {"hits": hits, "texts": texts, "source": source, "fallback_reason": fallback_reason, "nodes": nodes}


def reciprocal_rank_fusion(legs: dict[str, tuple[float, list[tuple[str, float]]]], k: int = RRF_K) -> dict[str, dict]:
    """
    Applies Reciprocal Rank Fusion (RRF) to merge ranked candidate lists from several channels.
    RRF Score(d) = Sum_{m in channels} [ w_m / (k + rank_m(d)) ]
    """
    fused: dict[str, dict] = {}
    for leg, (weight, ranked) in legs.items():
        for rank, (cid, sc) in enumerate(ranked):
            d = fused.setdefault(cid, {"score": 0.0, "legs": {}})
            d["score"] += weight / (k + rank + 1)
            d["legs"][leg] = {"rank": rank + 1, "score": round(sc, 4)}
    return fused


def hybrid_search(query: str, filters: dict | None = None, top_k: int = 10, mode: str = "hybrid",
                  reference: dict | None = None, alpha: float = 0.6) -> dict:
    """mode: hybrid | semantic | keyword. alpha weights the semantic leg in RRF.
    With a reference incident, hybrid mode adds a third leg: profile matches over all 100k cases."""
    t0 = time.time()
    store.load()
    pool_k = max(top_k * 3, 20)
    sem_query = f"{query} {filters_to_text(filters)}".strip()
    fut_kw = _pool.submit(lexical_search, sem_query, filters, pool_k) if mode in ("hybrid", "keyword") else None
    sem = semantic_search_synapt(sem_query, filters, top_k, pool_k) if mode in ("hybrid", "semantic") else         {"hits": [], "texts": {}, "source": None, "fallback_reason": None, "nodes": []}
    kw_hits = fut_kw.result() if fut_kw else []
    prof_hits = profile_matches(reference, filters, pool_k) if (reference and mode == "hybrid") else []

    fused = reciprocal_rank_fusion({
        "semantic": (alpha if mode == "hybrid" else 1.0, sem["hits"]),
        "keyword": ((1 - alpha) if mode == "hybrid" else 1.0, kw_hits),
        "profile": (alpha, prof_hits),
    })

    ranked = sorted(fused.items(), key=lambda kv: -kv[1]["score"])
    results = []
    for cid, d in ranked:
        c = store.get_case(cid)
        if not c:
            continue
        c["retrieval_score"] = round(d["score"] * 1000, 3)
        c["legs"] = d["legs"]
        c["similarity"] = similarity(c, reference)
        c["from_synapt"] = cid in sem["texts"]
        results.append(c)
    if reference:
        # rerank: blend fused score with attribute similarity
        mx = max((r["retrieval_score"] for r in results), default=1) or 1
        for r in results:
            r["rank_score"] = 0.5 * r["retrieval_score"] / mx + 0.5 * (r["similarity"] or 0)
        results.sort(key=lambda r: -r["rank_score"])
    results = results[:top_k]
    return {
        "query": query, "mode": mode, "filters": filters or {}, "count": len(results),
        "semantic_source": sem["source"] if mode != "keyword" else None,
        "fallback_reason": sem["fallback_reason"], "latency_ms": int((time.time() - t0) * 1000),
        "results": results, "knowledge_nodes": sem["nodes"],
    }


LABEL_FIELDS = ("disruption_type", "industry", "supplier_region", "response_type")


def synapt_label(text: str, k: int = 20) -> dict:
    """Label an incident from its nearest Synapt neighbours (the same idea as trident_label_ticket:
    rank what the most similar labelled cases are labelled), used while no ticket store exists."""
    store.load()
    hits = syn.get_chunks(text, top_k=k)
    neigh, seen = [], set()
    for h in hits:
        cid = h.get("id")
        if cid and cid not in seen and (c := store.get_case(cid)):
            seen.add(cid)
            neigh.append((len(neigh), c))
    if not neigh:
        return {"method": "synapt-knn", "neighbours": 0, "fields": {}, "fastest_response": []}
    fields = {}
    for f in LABEL_FIELDS:
        tally: dict = {}
        for rank, c in neigh:
            w = 1 / (1 + 0.15 * rank)
            t = tally.setdefault(c[f], {"w": 0.0, "n": 0, "example": c["disruption_id"]})
            t["w"] += w
            t["n"] += 1
        tot = sum(t["w"] for t in tally.values())
        fields[f] = [{"value": v, "confidence": round(t["w"] / tot, 3), "support": t["n"], "example": t["example"]}
                     for v, t in sorted(tally.items(), key=lambda kv: -kv[1]["w"])[:3]]
    by_resp: dict = {}
    for _, c in neigh:
        by_resp.setdefault(c["response_type"], []).append(c["full_recovery_days"])
    fastest = sorted(({"strategy": r, "cases": len(v), "avg_full_recovery": round(sum(v) / len(v), 1)}
                      for r, v in by_resp.items() if len(v) >= 2), key=lambda d: d["avg_full_recovery"])
    return {"method": "synapt-knn", "neighbours": len(neigh), "fields": fields, "fastest_response": fastest,
            "neighbour_ids": [c["disruption_id"] for _, c in neigh[:10]]}


def hybrid_retrieval_node(state: dict) -> dict:
    """LangGraph node (Investigation agent, part 1): hybrid search for similar historical cases,
    running in parallel with the Synapt worker."""
    from agents.state import describe, emit

    t0 = time.time()
    emit("agent_start", "investigator")
    payload, incident = state["payload"], state["incident"]
    search = hybrid_search(f"{state['query']}. {describe(incident)}", payload.get("filters"),
                           top_k=payload.get("top_k", 8), mode="hybrid", reference=incident)
    return {"search": search, "investigation_t0": t0}


def evidence_fusion_node(state: dict) -> dict:
    """LangGraph node (Investigation agent, part 2): joins the parallel branches. Adds graph-RAG cases
    that hybrid search did not return, then reports the investigation result."""
    from agents.state import done

    search, graph = state["search"], state.get("graph")
    cases = list(search["results"])
    if graph and graph.get("cases"):
        have = {c["disruption_id"] for c in cases}
        for gc in graph["cases"][:4]:
            c = store.get_case(gc["id"])
            if c and c["disruption_id"] not in have:
                c.update(similarity=similarity(c, state["incident"]), legs={"graph": {"rank": 0}}, from_synapt=True,
                         retrieval_score=None)
                cases.append(c)
    sims = [c["similarity"] for c in cases if c.get("similarity") is not None]
    summ = (f"{len(cases)} similar cases (avg similarity {np.mean(sims):.0%}) via "
            f"{search['semantic_source']} + BM25" + (", graph-RAG answer received" if graph and graph.get("answer") else ""))
    entry = done("investigator", state["investigation_t0"], summ,
                 {"search": {k: v for k, v in search.items() if k != "results"}, "cases": cases, "graph": graph})
    return {"cases": cases, "trace": [entry]}
