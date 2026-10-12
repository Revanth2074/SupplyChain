"""
Synapt Context Substrate Tool & Worker Node.
Invokes Synapt MCP tools (trident_query, trident_get_procedures, trident_get_chunks, trident_search,
trident_episodes, trident_label_ticket, trident_cypher, trident_feedback, trident_get_stats) via
SynaptMCPConnector to retrieve grounded graph, document and procedural context.

Synapt is required: the app runs in a single Synapt-backed mode. Every call has a timeout and any
failure raises SynaptError, which surfaces to the caller (there is no local fallback).
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import logging
import re
import threading
import time
from typing import Any

from config import settings
from agents.base import Action, Agent, Tool
from synapt.synapt_connector import SynaptConfig, SynaptError, SynaptMCPConnector

log = logging.getLogger("synapt.svc")

CASE_SPLIT = re.compile(r"#{2,3}\s*(DIS-\d{6})")
_pool = cf.ThreadPoolExecutor(max_workers=4)
_agent_pool = cf.ThreadPoolExecutor(max_workers=4)  # agent-level fan-out; tool calls inside use _pool


_last_error = {"tool": None, "error": ""}


class _RegionMap:
    """Synapt's PII masking rewrites supplier regions in ingested text to stable
    [LOCATION_<hash>] tokens (the same region always gets the same token). We learn
    token -> region from retrieved cases (DIS-id -> CSV) so queries can carry the
    token and answers can be shown with real region names."""

    FILE = settings.ARTIFACT_DIR / "synapt_region_tokens.json"
    TOKEN = re.compile(r"\[LOCATION_[0-9a-f]+\](?:\s*/\s*\[LOCATION_[0-9a-f]+\])*")
    IN_CASE = re.compile(r"Supplier region: (.*?)\. Supplier size")
    ALIASES = {
        "Africa/Middle East": r"Africa\s*/\s*Middle East|Middle East|Africa",
        "Asia-Pacific": r"Asia[- ]Pacific|APAC",
        "North America": r"North America",
        "South America": r"South America|Latin America",
        "Europe": r"Europe(?:an)?",
    }

    def __init__(self) -> None:
        self._lock = threading.Lock()
        try:
            data = json.loads(self.FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        self.tokens: dict[str, str] = data.get(settings.SYNAPT_PROVIDER_ID, {})
        self._all = data

    def learn(self, masked: str, region: str) -> None:
        masked = (masked or "").strip()
        if not self.TOKEN.fullmatch(masked) or self.tokens.get(masked) == region:
            return
        with self._lock:
            self.tokens[masked] = region
            self._all[settings.SYNAPT_PROVIDER_ID] = self.tokens
            try:
                self.FILE.write_text(json.dumps(self._all, indent=1, sort_keys=True), encoding="utf-8")
            except OSError as e:
                log.warning("could not persist region tokens: %s", e)

    def token_for(self, region: str) -> str | None:
        return next((t for t, r in self.tokens.items() if r == region), None)

    def mask(self, text: str) -> str:
        """Annotate region mentions with their Synapt token: 'Europe' -> 'Europe ([LOCATION_x])'."""
        for region, pat in self.ALIASES.items():
            tok = self.token_for(region)
            if tok:
                text = re.sub(rf"\b(?:{pat})\b", lambda m, t=tok: f"{m.group(0)} ({t})", text, count=1, flags=re.I)
        return text

    def unmask(self, text: str) -> str:
        if not text or "[LOCATION_" not in text:
            return text
        text = self.TOKEN.sub(lambda m: self.tokens.get(re.sub(r"\s+", "", m.group(0)), m.group(0)), text)
        # 'Europe (Europe)' left over from a masked query echoed back by the LLM
        return re.sub(r"\b([A-Z][\w/ -]+?) \(\1\)", r"\1", text)


regions = _RegionMap()


_connector_instance: SynaptMCPConnector | None = None
_connector_lock = threading.Lock()


def get_synapt_connector() -> SynaptMCPConnector:
    """Singleton getter for Synapt MCP connector."""
    global _connector_instance
    if _connector_instance is None:
        with _connector_lock:
            if _connector_instance is None:
                config = SynaptConfig()
                connector = SynaptMCPConnector(config)
                connector.authenticate()
                connector.initialize_mcp()
                _connector_instance = connector
    return _connector_instance


def configured() -> bool:
    return bool(settings.SYNAPT_USERNAME and settings.SYNAPT_PASSWORD and settings.SYNAPT_PROVIDER_ID)


def require_configured() -> None:
    if not configured():
        raise SynaptError("Synapt is not configured: set SYNAPT_USERNAME, SYNAPT_PASSWORD and "
                          "SYNAPT_PROVIDER_ID in backend/.env")


def _unwrap(r: Any) -> Any:
    """Connector returns the tool's JSON text; parse it (and unwrap {"result": "<json>"} envelopes)."""
    if isinstance(r, str):
        try:
            r = json.loads(r)
        except json.JSONDecodeError:
            return r
    if isinstance(r, dict) and set(r) == {"result"} and isinstance(r["result"], str):
        try:
            return json.loads(r["result"])
        except json.JSONDecodeError:
            return r["result"]
    return r


def _call(tool: str, args: dict, timeout: float) -> Any:
    require_configured()
    # provider_id / top_k / graph_hops are injected by the connector where the tool schema expects them
    fut = _pool.submit(lambda: get_synapt_connector().call_tool(tool, args))
    try:
        r = _unwrap(fut.result(timeout=timeout))
        _last_error.update(tool=None, error="")
        return r
    except cf.TimeoutError as e:
        _last_error.update(tool=tool, error=f"timed out after {timeout}s")
        raise SynaptError(f"{tool} timed out after {timeout}s") from e
    except Exception as e:  # noqa: BLE001
        _last_error.update(tool=tool, error=str(e)[:300])
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
    res = _call("trident_get_chunks", {"query": regions.mask(query),
                                       "top_k": top_k or settings.SYNAPT_TOP_K}, timeout)
    chunks = res if isinstance(res, list) else (res or {}).get("chunks", [])
    hits, rank = [], 0
    for ch in chunks:
        cases = split_cases(ch.get("text", ""))
        if not cases:  # aggregate stats or other prose
            hits.append({"id": None, "chunk_id": ch.get("chunk_id"), "text": regions.unmask(ch.get("text", "")),
                         "rank": rank, "source": "synapt"})
            rank += 1
        for cid, txt in cases:
            m = regions.IN_CASE.search(txt)
            hits.append({"id": cid, "chunk_id": ch.get("chunk_id"), "text": regions.unmask(txt), "rank": rank,
                         "source": "synapt", "masked_region": m.group(1) if m else None})
            rank += 1
    return hits


def search_nodes(query: str, top_k: int = 5, timeout: float = 25) -> list[dict]:
    """Semantic search over knowledge-graph nodes (procedures, steps, entities) via trident_search."""
    res = _call("trident_search", {"query": regions.mask(query), "top_k": top_k}, timeout)
    nodes = res if isinstance(res, list) else (res or {}).get("results", [])
    return [{"node_id": n.get("node_id"), "node_type": n.get("node_type"), "text": regions.unmask(n.get("text", "")),
             "score": round(float(n.get("score") or 0), 4), "rank": i + 1} for i, n in enumerate(nodes)]


def fetch_synapt_rag(question: str, top_k: int | None = None, hops: int | None = None, timeout: float = 90,
                     source: str = "workflow") -> dict:
    """Queries trident_query for a grounded answer, reasoning subgraph, chunks and quality signals."""
    return graph_query(question, top_k, hops, timeout, source)


def fetch_synapt_procedures(query: str = "disruption response playbook") -> list[dict]:
    """Retrieves SOP procedures and ordered steps from Synapt's Procedure Store."""
    return procedures(query)


def _node_name(label: str | None, props: dict) -> str:
    name = props.get("name") or props.get("filename")
    if not name and props.get("description"):
        name = props["description"][:70]
    if not name and props.get("step_number") is not None:
        name = f"Step {props['step_number']}"
    return regions.unmask(name or label or "node")


def graph_query(question: str, top_k: int | None = None, hops: int | None = None, timeout: float = 90,
                source: str = "app") -> dict:
    """Graph-augmented RAG via trident_query (answer + subgraph + chunks + quality signals)."""
    r = _call("trident_query", {
        "question": regions.mask(question), "top_k": top_k or settings.SYNAPT_TOP_K,
        "graph_hops": hops if hops is not None else settings.SYNAPT_GRAPH_HOPS, "ticket_mode": "auto",
    }, timeout)
    if not isinstance(r, dict):
        return {"answer": str(r)}
    sg = r.get("reasoning_subgraph") or {}
    nodes = []
    for n in sg.get("nodes", []):
        props = n.get("properties") or {}
        nodes.append({
            "id": n.get("node_id"), "type": n.get("label"), "name": _node_name(n.get("label"), props),
            "description": regions.unmask(props.get("description", "")),
            "relevance": n.get("relevance"), "hop": n.get("hop_distance"), "centrality": n.get("centrality"),
            "confidence": props.get("confidence"), "health": props.get("health"),
        })
    edges = [{"source": e.get("source"), "target": e.get("target"), "type": e.get("edge_type"),
              "confidence": e.get("confidence")} for e in sg.get("edges", [])]
    cases = []
    for ch in r.get("chunks", []):
        for cid, txt in split_cases(ch.get("text", "")):
            cases.append({"id": cid, "text": regions.unmask(txt), "chunk_id": ch.get("chunk_id")})
    trust = r.get("trust_signal") or {}
    quality = {
        "confidence": r.get("confidence_score"), "knowledge_confidence": r.get("ks_confidence"),
        "procedural_confidence": r.get("ps_confidence"), "graph_confidence": r.get("graph_confidence"),
        "ticket_confidence": r.get("ts_confidence"), "rerank_delta": r.get("rerank_delta"),
        "degraded": bool(trust.get("degraded")), "degraded_reasons": trust.get("reasons") or [],
        "low_confidence_nodes": trust.get("low_confidence_node_count"),
        "nodes_dropped_by_budget": r.get("nodes_dropped_by_budget"), "stale_nodes_dropped": r.get("stale_nodes_dropped"),
        "avg_traversal_depth": r.get("avg_traversal_depth"), "intent": r.get("intent"),
        "stores_used": r.get("stores_used") or [], "stores_skipped": r.get("stores_skipped") or {},
        "seed_latency_ms": r.get("seed_latency_ms"), "retrieval_latency_ms": r.get("retrieval_latency_ms"),
        "traversal_s": r.get("traversal_time"), "warnings": r.get("warnings") or [],
    }
    out = {
        "query_id": r.get("query_id"), "task_id": r.get("task_id"), "answer": regions.unmask(r.get("answer", "")),
        "confidence": quality["confidence"], "graph_confidence": quality["graph_confidence"],
        "knowledge_confidence": quality["knowledge_confidence"], "intent": quality["intent"],
        "trust": trust, "stores_used": quality["stores_used"], "quality": quality,
        "procedures": r.get("procedures") or [],
        "ticket_labels": _ticket_labels(r.get("ticket_labels")) if r.get("ticket_labels") else None,
        "episodes_used": [{"id": e.get("episode_id"), "origin": e.get("origin"), "score": e.get("score"),
                           "summary": regions.unmask((e.get("summary") or "")[:400])}
                          for e in (r.get("episodes_used") or [])],
        "nodes": nodes, "edges": edges, "cases": cases, "latency_s": quality["traversal_s"],
    }
    try:
        from services import feedback
        feedback.log_synapt_quality(source, question, out["query_id"], quality)
    except Exception as e:  # noqa: BLE001
        log.debug("quality log failed: %s", e)
    return out


def procedures(query: str, timeout: float = 30) -> list[dict]:
    """Structured SOPs (trident_get_procedures) -> [{name, intent, steps:[{n, text, after}]}]."""
    res = _call("trident_get_procedures", {"query": query}, timeout)
    res = res if isinstance(res, list) else (res or {}).get("procedures", [])
    out = []
    for p in res:
        steps = sorted(p.get("steps") or [], key=lambda st: st.get("step_number") or 0)
        out.append({"name": p.get("name"), "intent": p.get("intent"), "source": "synapt",
                    "steps": [{"n": st.get("step_number"), "text": regions.unmask(st.get("description", "")),
                               "after": st.get("pre_requisite") or None} for st in steps]})
    return out


def procedure_for(disruption_type: str) -> dict | None:
    """The response playbook for one disruption type, if Synapt holds it."""
    want = f"respond to a {disruption_type} disruption".lower()
    procs = procedures(f"Respond to a {disruption_type} disruption")
    return next((p for p in procs if (p["name"] or "").lower() == want), None) or \
        next((p for p in procs if disruption_type.lower() in (p["name"] or "").lower()), None)


def episodes(query: str = "", top_k: int = 5, timeout: float = 30) -> dict:
    args: dict = {"top_k": top_k}
    if query:
        args["query"] = regions.mask(query)
    r = _call("trident_episodes", args, timeout)
    return r if isinstance(r, dict) else {"episodes": r}


def label_ticket(ticket: dict, fields: list[str] | None = None, timeout: float = 45) -> dict:
    """trident_label_ticket -> {field: [{value, confidence, support, example}]} (top candidates per field).
    The tool takes the ticket as a JSON *string* shaped like a row of the ingested dump."""
    args: dict = {"ticket": json.dumps(ticket)}
    if fields:
        args["fields"] = ",".join(fields)
    r = _call("trident_label_ticket", args, timeout)
    if isinstance(r, dict) and r.get("error"):
        raise SynaptError(str(r["error"]))
    return _ticket_labels(r)


def _ticket_labels(r: Any) -> dict:
    """Normalise ticket_labels (from label_ticket or trident_query) for the first ticket."""
    item = (r[0] if isinstance(r, list) and r else r) or {}
    if isinstance(item, dict) and "results" in item and isinstance(item["results"], list) and item["results"]:
        item = item["results"][0]
    fields = {}
    for name, f in ((item.get("fields") or {}) if isinstance(item, dict) else {}).items():
        labels = [{"value": lb.get("value"), "confidence": lb.get("confidence"), "support": lb.get("support"),
                   "example": (lb.get("example") or {}).get("ticket_id"),
                   "low_support": lb.get("low_support")} for lb in (f.get("labels") or [])[:3]]
        fields[name] = {"labels": labels, "reliability": f.get("reliability"), "coverage": f.get("coverage")}
    return {"fields": fields, "neighbours": ((item.get("assignment") or {}).get("neighbours_used")
                                              if isinstance(item, dict) else None)}


# Read-only Cypher templates. trident_cypher is NOT scoped by provider on the server
# (it can read every tenant's nodes), so every pattern is pinned to our provider_id
# and callers can only pick a template, never send raw Cypher.
GRAPH_INSIGHTS = {
    "playbook_strategy": (
        "Recommended strategy per disruption type",
        "The strategy-selection step of each Synapt response playbook.",
        "MATCH (p:Procedure)-[:HAS_STEP]->(s:Step) WHERE p.provider_id = '{pid}' AND s.provider_id = '{pid}' "
        "AND s.description CONTAINS 'response strategy' "
        "RETURN p.name AS playbook, s.description AS guidance ORDER BY playbook"),
    "backup_effect": (
        "Backup supplier effect by disruption type",
        "Playbook steps quantifying recovery with vs without a backup supplier.",
        "MATCH (p:Procedure)-[:HAS_STEP]->(s:Step) WHERE p.provider_id = '{pid}' AND s.provider_id = '{pid}' "
        "AND s.description CONTAINS 'backup' RETURN p.name AS playbook, s.description AS evidence ORDER BY playbook"),
    "procedures": (
        "Playbooks and their steps",
        "Every procedure in the knowledge graph with its step count.",
        "MATCH (p:Procedure) WHERE p.provider_id = '{pid}' OPTIONAL MATCH (p)-[:HAS_STEP]->(s:Step) "
        "RETURN p.name AS playbook, p.intent AS intent, count(s) AS steps ORDER BY playbook"),
    "strategies": (
        "Response strategies in the graph",
        "Strategy nodes extracted from the case documents, ranked by supporting evidence.",
        "MATCH (b:BusinessProcess) WHERE b.provider_id = '{pid}' "
        "RETURN b.name AS strategy, b.process_type AS type, b.confidence AS confidence, "
        "size(b.source_chunk_ids) AS evidence_chunks ORDER BY evidence_chunks DESC"),
    "node_types": (
        "Graph composition",
        "Node counts by type for this provider.",
        "MATCH (n) WHERE n.provider_id = '{pid}' RETURN labels(n)[0] AS node_type, count(*) AS nodes "
        "ORDER BY nodes DESC"),
    "edge_types": (
        "Relationship types",
        "Edge counts by type between this provider's nodes.",
        "MATCH (a)-[r]->(b) WHERE a.provider_id = '{pid}' AND b.provider_id = '{pid}' "
        "RETURN type(r) AS relationship, count(*) AS edges ORDER BY edges DESC"),
}


def graph_insight(key: str, timeout: float = 30) -> dict:
    if key not in GRAPH_INSIGHTS:
        raise SynaptError(f"unknown insight '{key}'")
    pid = settings.SYNAPT_PROVIDER_ID
    if not re.fullmatch(r"[\w-]+", pid):
        raise SynaptError("provider id not safe for Cypher")
    title, desc, tpl = GRAPH_INSIGHTS[key]
    t0 = time.time()
    rows = _call("trident_cypher", {"query": tpl.format(pid=pid)}, timeout)
    rows = rows if isinstance(rows, list) else []
    rows = [{k: regions.unmask(v) if isinstance(v, str) else v for k, v in r.items()} for r in rows]
    return {"key": key, "title": title, "description": desc, "cypher": tpl.format(pid=pid), "rows": rows,
            "latency_ms": int((time.time() - t0) * 1000)}


def send_feedback(feedback_id: str, verdict: str, score: float | None, reason: str | None) -> Any:
    """Write the operator's verdict on a trident_query answer back to Synapt episodic memory."""
    return _call("trident_feedback", {
        "feedback_id": feedback_id, "caller_type": "user", "verdict": verdict,
        "score": score, "reason": reason, "post_action": "proceeded",
    }, 20)


def stats(timeout: float = 15) -> dict:
    r = _call("trident_get_stats", {}, timeout)
    return r if isinstance(r, dict) else {"raw": r}


def status() -> dict:
    return {"configured": configured(), "last_failed_tool": _last_error["tool"],
            "last_error": _last_error["error"],
            "provider_id": settings.SYNAPT_PROVIDER_ID, "mcp_url": settings.SYNAPT_MCP_URL,
            "region_tokens_learned": len(regions.tokens)}


MIN_GRAPH_CONFIDENCE = 0.5   # a graph-RAG answer below this is treated as weak


def _graph_and_playbook(question: str | None, disruption_type: str | None) -> dict:
    """Ask graph-RAG and fetch the playbook in parallel (either may be skipped)."""
    gf = _agent_pool.submit(fetch_synapt_rag, question, None, None, 75, "workflow") if question else None
    pf = _agent_pool.submit(procedure_for, disruption_type) if disruption_type else None
    return {"graph": gf.result(timeout=80) if gf else None, "procedure": pf.result(timeout=30) if pf else None}


class SynaptAgent(Agent):
    """Goal: a confident, grounded graph-RAG answer for this incident plus the response playbook for its
    disruption type. Tools: trident_query (graph-RAG) and trident_get_procedures, run in parallel. The
    agent grades Synapt's own confidence; when the answer is missing or weak it re-asks one broader
    question (type + industry) and keeps the stronger answer. Synapt is required: a failure stops the
    workflow with SynaptError (there is no local fallback)."""

    id, node = "investigator", "synapt_worker"
    goal = f"Get a graph-RAG answer with confidence >= {MIN_GRAPH_CONFIDENCE:.0%} and the response playbook"
    max_steps = 2
    reports_done = False  # reported together with the case search by the Evidence-fusion step

    def make_tools(self) -> list[Tool]:
        return [Tool("graph_rag_and_playbook", "trident_query + trident_get_procedures in parallel",
                     lambda question, disruption_type: _graph_and_playbook(question, disruption_type)),
                Tool("graph_rag", "trident_query: grounded answer, subgraph and quality signals",
                     lambda question: _graph_and_playbook(question, None))]

    def perceive(self, state: dict) -> dict:
        from agents.state import describe
        require_configured()
        payload, incident = state["payload"], state["incident"]
        desc = state.get("description") or ""
        core = {k: incident.get(k) for k in ("disruption_type", "industry")}
        return {"use_graph": payload.get("use_graph", True), "incident": incident,
                "specific": (f"{describe(incident)}. {desc[:300]} Has a similar disruption occurred and how was it "
                             f"resolved, which response strategy recovered fastest?"),
                "broad": f"How are {describe(core)}s usually resolved, and which response strategy recovers fastest?",
                "graph": None, "procedure": state.get("procedure"), "asked": 0,
                "round": state.get("synapt_round", 0) + 1}

    @staticmethod
    def _strong(g: dict | None) -> bool:
        return bool(g and g.get("answer") and (g.get("confidence") or 0) >= MIN_GRAPH_CONFIDENCE)

    def decide(self, obs: dict, steps: list[dict]) -> Action | None:
        if not steps:
            q = obs["specific"] if obs["use_graph"] else None
            what = "Ask graph-RAG about this incident" if q else "Graph-RAG is off for this run"
            return Action("graph_rag_and_playbook", {"question": q, "disruption_type": obs["incident"]["disruption_type"]},
                          f"{what} and fetch the {obs['incident']['disruption_type']} playbook, in parallel")
        if obs["use_graph"] and not self._strong(obs["graph"]) and obs["asked"] < 2:
            g = obs["graph"] or {}
            why = "no answer" if not g.get("answer") else f"confidence {g.get('confidence', 0):.0%} is weak"
            return Action("graph_rag", {"question": obs["broad"]}, f"Graph-RAG gave {why}: ask a broader question")
        return None

    def observe(self, obs: dict, action, result, error):
        if action.tool == "graph_rag_and_playbook":
            obs["procedure"] = result["procedure"] or obs["procedure"]
        g = result["graph"]
        if g is not None:
            obs["asked"] += 1
            old = obs["graph"]
            if old is None or (g.get("answer") and (g.get("confidence") or 0) > (old.get("confidence") or 0)) or not old.get("answer"):
                g["question_kind"] = "specific" if action.tool == "graph_rag_and_playbook" else "broad"
                obs["graph"] = g
        return obs

    def summarise(self, action, result, error):
        g, p = result.get("graph"), result.get("procedure")
        parts = []
        if g is not None:
            parts.append(f"answer {'received' if g.get('answer') else 'missing'}, confidence {g.get('confidence') or 0:.2f}")
        if action.tool == "graph_rag_and_playbook":
            parts.append(f"playbook: {p['name']} ({len(p['steps'])} steps)" if p else "no playbook found")
        return " · ".join(parts)

    def reflect(self, obs: dict, steps: list[dict]) -> dict:
        g, p = obs["graph"], obs["procedure"]
        ok = (self._strong(g) or not obs["use_graph"]) and p is not None
        return {"status": "done" if ok else "partial", "confidence": (g or {}).get("confidence"),
                "summary": (("graph-RAG answer" + (f" (confidence {g.get('confidence') or 0:.2f})" if g else "")
                             if g and g.get("answer") else "no graph-RAG answer")
                            + (f" · playbook {p['name']}" if p else " · no playbook")),
                "requests": []}

    def commit(self, obs: dict, message: dict, state: dict) -> dict:
        return {"graph": obs["graph"], "procedure": obs["procedure"], "synapt_round": obs["round"]}


synapt_worker_node = SynaptAgent()
