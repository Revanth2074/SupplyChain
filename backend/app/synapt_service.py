"""High-level Synapt service: semantic chunk retrieval, graph-RAG query,
feedback, plus a circuit breaker so the app falls back to local search."""
from __future__ import annotations

import concurrent.futures as cf
import json
import logging
import re
import time
from typing import Any

from .config import settings
from .synapt_client import SynaptError, get_client

log = logging.getLogger("synapt.svc")

CASE_SPLIT = re.compile(r"#{2,3}\s*(DIS-\d{6})")
_pool = cf.ThreadPoolExecutor(max_workers=4)


class _Breaker:
    def __init__(self, threshold: int = 3, cooldown: int = 60) -> None:
        self.fails, self.threshold, self.cooldown, self.opened = 0, threshold, cooldown, 0.0
        self.last_error = ""

    def allow(self) -> bool:
        return self.fails < self.threshold or time.time() - self.opened > self.cooldown

    def ok(self) -> None:
        self.fails, self.last_error = 0, ""

    def fail(self, e: Exception) -> None:
        self.fails += 1
        self.last_error = str(e)[:300]
        if self.fails >= self.threshold:
            self.opened = time.time()


breaker = _Breaker()


def configured() -> bool:
    return bool(settings.SYNAPT_USERNAME and settings.SYNAPT_PASSWORD and settings.SYNAPT_PROVIDER_ID)


def _unwrap(r: Any) -> Any:
    if isinstance(r, dict) and set(r) == {"result"} and isinstance(r["result"], str):
        try:
            return json.loads(r["result"])
        except json.JSONDecodeError:
            return r["result"]
    return r


def _call(tool: str, args: dict, timeout: float) -> Any:
    if not configured():
        raise SynaptError("Synapt not configured")
    if not breaker.allow():
        raise SynaptError(f"Synapt circuit open: {breaker.last_error}")
    args = {"provider_id": settings.SYNAPT_PROVIDER_ID, **args}
    fut = _pool.submit(get_client().call_tool, tool, args)
    try:
        r = _unwrap(fut.result(timeout=timeout))
        breaker.ok()
        return r
    except cf.TimeoutError as e:
        breaker.fail(e)
        raise SynaptError(f"{tool} timed out after {timeout}s") from e
    except Exception as e:  # noqa: BLE001
        breaker.fail(e)
        raise SynaptError(f"{tool} failed: {e}") from e


def split_cases(text: str) -> list[tuple[str, str]]:
    """Split a chunk into (DIS-id, case_text) pairs."""
    parts = CASE_SPLIT.split(text or "")
    out = []
    for i in range(1, len(parts) - 1, 2):
        out.append((parts[i], parts[i + 1].strip()))
    return out


def get_chunks(query: str, top_k: int | None = None, timeout: float = 25) -> list[dict]:
    """Semantic retrieval over ingested case documents -> list of case hits."""
    res = _call("trident_get_chunks", {"query": query, "top_k": top_k or settings.SYNAPT_TOP_K}, timeout)
    chunks = res if isinstance(res, list) else (res or {}).get("chunks", [])
    hits, rank = [], 0
    for ch in chunks:
        cases = split_cases(ch.get("text", ""))
        if not cases:  # aggregate stats or other prose
            hits.append({"id": None, "chunk_id": ch.get("chunk_id"), "text": ch.get("text", ""),
                         "rank": rank, "source": "synapt"})
            rank += 1
        for cid, txt in cases:
            hits.append({"id": cid, "chunk_id": ch.get("chunk_id"), "text": txt, "rank": rank, "source": "synapt"})
            rank += 1
    return hits


def graph_query(question: str, top_k: int | None = None, hops: int | None = None, timeout: float = 90) -> dict:
    """Graph-augmented RAG via trident_query (answer + subgraph + chunks)."""
    r = _call("trident_query", {
        "question": question, "top_k": top_k or settings.SYNAPT_TOP_K,
        "graph_hops": hops if hops is not None else settings.SYNAPT_GRAPH_HOPS, "ticket_mode": "off",
    }, timeout)
    if not isinstance(r, dict):
        return {"answer": str(r)}
    sg = r.get("reasoning_subgraph") or {}
    nodes = [{
        "id": n.get("node_id"), "type": n.get("label"),
        "name": (n.get("properties") or {}).get("name"),
        "description": (n.get("properties") or {}).get("description", ""),
        "relevance": n.get("relevance"), "hop": n.get("hop_distance"),
        "confidence": (n.get("properties") or {}).get("confidence"),
    } for n in sg.get("nodes", [])]
    edges = [{"source": e.get("source"), "target": e.get("target"), "type": e.get("edge_type"),
              "confidence": e.get("confidence")} for e in sg.get("edges", [])]
    cases = []
    for ch in r.get("chunks", []):
        for cid, txt in split_cases(ch.get("text", "")):
            cases.append({"id": cid, "text": txt, "chunk_id": ch.get("chunk_id")})
    return {
        "query_id": r.get("query_id"), "task_id": r.get("task_id"), "answer": r.get("answer", ""),
        "confidence": r.get("confidence_score"), "graph_confidence": r.get("graph_confidence"),
        "knowledge_confidence": r.get("ks_confidence"), "intent": r.get("intent"),
        "trust": r.get("trust_signal"), "stores_used": r.get("stores_used"),
        "nodes": nodes, "edges": edges, "cases": cases,
        "latency_s": r.get("traversal_time"),
    }


def send_feedback(feedback_id: str, verdict: str, score: float | None, reason: str | None) -> Any:
    return get_client().call_tool("trident_feedback", {
        "feedback_id": feedback_id, "caller_type": "user", "verdict": verdict,
        "score": score, "reason": reason, "post_action": "proceeded",
    })


def stats(timeout: float = 15) -> dict:
    r = _call("trident_get_stats", {}, timeout)
    return r if isinstance(r, dict) else {"raw": r}


def status() -> dict:
    return {"configured": configured(), "circuit_open": not breaker.allow(),
            "consecutive_failures": breaker.fails, "last_error": breaker.last_error,
            "provider_id": settings.SYNAPT_PROVIDER_ID, "mcp_url": settings.SYNAPT_MCP_URL}
