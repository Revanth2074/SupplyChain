"""
Hybrid Retrieval Engine & Reciprocal Rank Fusion (RRF) Node.
Fuses Synapt Context Substrate semantic retrieval (trident_get_chunks, joined back to the CSV) with
lexical BM25 candidates from the 100k-case index and an attribute-profile leg over all 100k rows;
trident_search adds knowledge-graph nodes (playbook procedures and steps).
Synapt is required: there is no local semantic fallback, and a Synapt failure raises SynaptError.
"""
from __future__ import annotations

import concurrent.futures as cf
import time

import numpy as np

from agents import synapt_tools as syn
from agents.base import Action, Agent, Tool
from agents.state import describe
from services.data_store import store

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


def semantic_search_synapt(query: str, filters: dict | None, top_k: int) -> dict:
    """Semantic leg via the Synapt Context Substrate: trident_get_chunks (case documents, joined back to
    the CSV by DIS- id) plus trident_search (knowledge-graph nodes: playbook procedures and steps) returned
    as supporting knowledge. Synapt is required; a failure raises SynaptError."""
    hits: list[tuple[str, float]] = []
    texts: dict[str, str] = {}
    node_fut = _pool.submit(syn.search_nodes, query, 5)
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
    return {"hits": hits, "texts": texts, "source": "synapt", "nodes": node_fut.result(timeout=30)}


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
    sem = semantic_search_synapt(sem_query, filters, top_k) if mode in ("hybrid", "semantic") else         {"hits": [], "texts": {}, "source": None, "nodes": []}
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
        "semantic_source": sem["source"], "latency_ms": int((time.time() - t0) * 1000),
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


MIN_CASES = 3            # fewer precedents than this is thin evidence
MIN_SIMILARITY = 0.6     # average attribute similarity below this is weak evidence


def _quality(search: dict) -> tuple[int, float | None]:
    sims = [c["similarity"] for c in search["results"] if c.get("similarity") is not None]
    return len(search["results"]), (float(np.mean(sims)) if sims else None)


def _good(n: int, sim: float | None) -> bool:
    return n >= MIN_CASES and (sim is None or sim >= MIN_SIMILARITY)


class CaseRetrievalAgent(Agent):
    """Goal: at least MIN_CASES similar precedents with average similarity >= MIN_SIMILARITY.
    Tools: hybrid search (Synapt trident_get_chunks + BM25 + profile, fused by RRF) run with three
    strategies of increasing breadth. The agent judges its own evidence and widens the search itself;
    it keeps the best result it found. The supervisor can ask it to start broad (revision) or to focus
    on the incident's exact disruption type (when the Judge finds the analysis off-target)."""

    id, node = "investigator", "hybrid_retriever"
    goal = f"Find at least {MIN_CASES} precedents with average similarity of {MIN_SIMILARITY:.0%} or more"
    max_steps = 3
    reports_done = False  # the investigation result is reported once the evidence is fused

    def make_tools(self) -> list[Tool]:
        return [Tool("hybrid_search", "Synapt semantic + BM25 + profile search fused by Reciprocal Rank Fusion",
                     lambda **kw: hybrid_search(**kw))]

    def perceive(self, state: dict) -> dict:
        payload, incident = state["payload"], state["incident"]
        plan = state.get("retrieval_plan") or {}
        top_k = payload.get("top_k", 8)
        t = incident.get("disruption_type")
        ladder = [
            ("focused", f"{state['query']}. {describe(incident)}",
             {"disruption_type": [t]} if plan.get("focus") and t else payload.get("filters"), top_k),
            ("broadened", describe({k: incident.get(k) for k in ("disruption_type", "industry")}), None, top_k + 4),
            ("type-only", describe({"disruption_type": t}), {"disruption_type": [t]} if t else None, top_k + 6),
        ]
        start = 1 if plan.get("broaden") else 0
        return {"incident": incident, "ladder": ladder[start:], "tried": [], "best": None, "best_q": None,
                "round": state.get("retrieval_round", 0) + 1, "t0": time.time(), "plan": plan}

    def decide(self, obs: dict, steps: list[dict]) -> Action | None:
        if obs["best"] is not None and _good(*_quality(obs["best"])):
            return None  # goal met
        i = len(obs["tried"])
        if i >= len(obs["ladder"]):
            return None  # every strategy tried: keep the best evidence found
        name, query, filters, k = obs["ladder"][i]
        if i == 0:
            if obs["plan"].get("focus"):
                thought = "Search focused on the incident's exact disruption type"
            elif obs["plan"].get("broaden"):
                thought = "Asked for wider evidence: start with a broadened search"
            else:
                thought = "Search with the full incident description" + (" and the user's filters" if filters else "")
        else:
            n, sim = _quality(obs["best"])
            why = f"only {n} case(s)" if n < MIN_CASES else f"average similarity {sim:.0%} is below {MIN_SIMILARITY:.0%}"
            thought = f"Evidence is weak ({why}): try a {name} search with more candidates"
        return Action("hybrid_search", {"query": query, "filters": filters, "top_k": k, "mode": "hybrid",
                                        "reference": obs["incident"]}, thought)

    def observe(self, obs: dict, action: Action, result, error: str | None) -> dict:
        name = obs["ladder"][len(obs["tried"])][0]
        obs["tried"].append(name)
        n, sim = _quality(result)
        score = (sim or 0) * min(1.0, n / MIN_CASES)
        if obs["best"] is None or score > obs["best_q"]:
            result["strategy"] = name
            obs["best"], obs["best_q"] = result, score
        return obs

    def summarise(self, action: Action, result, error: str | None) -> str:
        n, sim = _quality(result)
        return f"{n} cases, average similarity {sim:.0%} via {result['semantic_source']}" if sim is not None else f"{n} cases"

    def reflect(self, obs: dict, steps: list[dict]) -> dict:
        n, sim = _quality(obs["best"])
        ok = _good(n, sim)
        return {"status": "done" if ok else "partial", "confidence": round(sim, 2) if sim is not None else None,
                "summary": (f"{n} cases (avg similarity {sim or 0:.0%}) after {len(obs['tried'])} search(es), "
                            f"best: {obs['best']['strategy']}" + ("" if ok else " · evidence still thin")),
                "requests": []}

    def commit(self, obs: dict, message: dict, state: dict) -> dict:
        search = obs["best"]
        search.update(round=obs["round"], broadened=search["strategy"] != "focused", attempts=obs["tried"],
                      confidence=message["confidence"], evidence_ok=message["status"] == "done")
        return {"search": search, "investigation_t0": obs["t0"], "retrieval_round": obs["round"], "retrieval_plan": {}}


class EvidenceFusionAgent(Agent):
    """Goal: one evidence set for the analysis. Joins the parallel investigation branches: adds the
    cases Synapt's graph-RAG cited that hybrid search did not return, then grades the evidence
    (case similarity and Synapt's confidence) and reports the investigation result."""

    id, node = "investigator", "evidence_fusion"
    goal = "Merge case search and Synapt graph-RAG into one graded evidence set"
    max_steps = 1

    def make_tools(self) -> list[Tool]:
        return [Tool("merge_graph_cases", "Add the cases Synapt graph-RAG cited that search did not return",
                     lambda cases, graph, incident: _merge(cases, graph, incident))]

    def started_at(self, state: dict) -> float:
        return state.get("investigation_t0") or super().started_at(state)

    def perceive(self, state: dict) -> dict:
        return {"search": state["search"], "graph": state.get("graph"), "incident": state["incident"],
                "cases": list(state["search"]["results"]), "added": 0}

    def decide(self, obs: dict, steps: list[dict]) -> Action | None:
        if steps or not (obs["graph"] or {}).get("cases"):
            return None
        return Action("merge_graph_cases", {"cases": obs["cases"], "graph": obs["graph"], "incident": obs["incident"]},
                      "Synapt cited cases of its own: add any that search missed")

    def observe(self, obs: dict, action: Action, result, error: str | None) -> dict:
        obs["added"] = len(result) - len(obs["cases"])
        obs["cases"] = result
        return obs

    def summarise(self, action: Action, result, error: str | None) -> str:
        return f"{len(result)} cases after merging"

    def reflect(self, obs: dict, steps: list[dict]) -> dict:
        search, graph, cases = obs["search"], obs["graph"], obs["cases"]
        sims = [c["similarity"] for c in cases if c.get("similarity") is not None]
        sim = float(np.mean(sims)) if sims else None
        gconf = (graph or {}).get("confidence")
        parts = [v for v in (sim, gconf) if v is not None]
        attempts = search.get("attempts") or []
        summ = (f"{len(cases)} similar cases (avg similarity {sim or 0:.0%}) via {search['semantic_source']} + BM25"
                + (f", +{obs['added']} from Synapt" if obs["added"] else "")
                + (", graph-RAG answer received" if graph and graph.get("answer") else "")
                + (f" · {len(attempts)} search(es), best: {search.get('strategy')}" if len(attempts) > 1 else ""))
        return {"status": "done" if search.get("evidence_ok", True) else "partial",
                "confidence": round(sum(parts) / len(parts), 2) if parts else None, "summary": summ, "requests": []}

    def commit(self, obs: dict, message: dict, state: dict) -> dict:
        return {"cases": obs["cases"]}

    def detail(self, obs: dict):
        return {"search": {k: v for k, v in obs["search"].items() if k != "results"}, "cases": obs["cases"],
                "graph": obs["graph"]}


def _merge(cases: list[dict], graph: dict, incident: dict) -> list[dict]:
    out = list(cases)
    have = {c["disruption_id"] for c in out}
    for gc in graph["cases"][:4]:
        c = store.get_case(gc["id"])
        if c and c["disruption_id"] not in have:
            c.update(similarity=similarity(c, incident), legs={"graph": {"rank": 0}}, from_synapt=True, retrieval_score=None)
            out.append(c)
            have.add(c["disruption_id"])
    return out


hybrid_retrieval_node = CaseRetrievalAgent()
evidence_fusion_node = EvidenceFusionAgent()
