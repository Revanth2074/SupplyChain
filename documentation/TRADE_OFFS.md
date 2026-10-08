# Architectural Design Decisions & Trade-Off Analysis

## Executive Summary

The assistant splits work by what each engine is good at: **Synapt** holds the organisational knowledge
(cases, playbooks, graph, graph-RAG answers, episodic memory), **local ML** produces every number, rules
and templates assemble the briefing, and the external **LLM** is used only as the independent judge. The decisions below explain each choice and what
was given up for it.

## 1. Knowledge Substrate: Synapt Context Substrate vs. Generic Vector DBs

| | Vector DB (FAISS / pgvector) | Synapt Context Substrate |
|---|---|---|
| Similar passages | ✔ | ✔ (`trident_get_chunks`) |
| Reasoning path (multi-hop) | ✘ | ✔ graph-RAG subgraph (`trident_query`) |
| Procedures as ordered steps | ✘ (text blobs) | ✔ Procedure Store (`trident_get_procedures`) |
| Memory of outcomes | ✘ | ✔ episodes + `trident_feedback` |
| Answer quality signals | ✘ | ✔ knowledge / procedural / graph confidence, degraded flag |
| Protocol | proprietary SDK | open MCP (JSON-RPC over HTTP) |

**Measured:** Synapt's semantic leg finds the right disruption type 87 % of the time in the top 8 vs. 68.5 %
for the local LSA index (25 golden cases).
**Trade-off:** a network dependency on a beta service. Mitigated by per-tool circuit breakers and local
fallbacks (see `visual/synapt-modes.html`).

## 2. Storage Architecture: Hybrid Dual-Persistence (Synapt + Local Store)

### The Trade-Off
Ingesting 100,000 long narratives into Synapt is slow and costly, but the ML models and statistics need
every row.

### The Solution: Hybrid Dual-Persistence
- **Synapt:** 4,000 case narratives, profiles and statistics over all 100k rows, 6 SOP playbooks, tickets.
- **Local:** all 100k rows in memory (BM25 + LSA + vectorised profile matching), SQLite for operational state.
- Every Synapt hit is joined back to its CSV row by `DIS-` ID, so the two stores never disagree on facts.
- The profile leg over all 100k rows raised exact-profile matches from 14 % to 83 %.

## 3. Reasoning & LLM Strategy: Synapt Reasons, the LLM Only Judges

- Following the reference capstone, no agent calls an external LLM. Classification uses vocabulary-constrained
  keyword rules (98/98 fields on the golden set), the plan comes from strategy statistics plus the Synapt
  playbook steps, the briefing is built from the evidence plus Synapt's graph-RAG answer, and `/ask` returns
  Synapt's `trident_query` answer.
- Numbers come from gradient-boosting models (P10–P90 ranges) and the dataset; a deterministic fact-check
  rejects unknown case IDs, placeholders and amounts/percentages not in the evidence or the Synapt playbook.
- The aicredits.in model is the independent judge: `scripts/llm_judge.py` (4 rubrics), DeepEval and
  `POST /api/judge`. Keeping the judge separate from the generator avoids a model grading its own text.
- **Trade-off:** briefings read more like structured reports than prose, and unusual wording relies on keyword
  rules. In return a full analysis costs no LLM credits, cannot be broken by a gateway outage or budget limit,
  and runs in ≈ 13 s.

## 4. Multi-Agent Orchestration: LangGraph StateGraph vs. Monolithic ReAct Agent

### Why Monolithic ReAct Was Rejected
- Non-deterministic tool order makes results hard to audit and evaluate.
- One prompt mixing retrieval, prediction and writing invites hallucinated numbers.
- Latency is unbounded (the agent decides how many tool calls to make).

### Why LangGraph StateGraph Was Chosen
- Explicit nodes with one responsibility each and a typed `DisruptionAgentState`.
- **Parallel fan-out:** hybrid retrieval and the Synapt worker (graph-RAG + playbook) run concurrently and
  join in `evidence_fusion`.
- **Conditional edge:** invalid input (guardrail violation) goes straight to END before any model call.
- **Streaming:** each node emits `agent_start` / `agent_done` events (`stream_mode="custom"`) for the console.
- **Trade-off:** less autonomy than a free-form agent; deliberate, because operational decisions need to be
  reproducible.

## 5. Retrieval Fusion: Reciprocal Rank Fusion vs. Weighted Scores

Cosine similarities, BM25 scores and profile scores live on different scales. RRF (k = 60) fuses by rank,
needs no calibration, and rewards agreement between legs. **Trade-off:** it ignores score magnitude.

## 6. Prediction: Gradient Boosting with Quantile Ranges

Tabular data, 100k rows, mostly categorical features → HistGradientBoosting (fast, accurate, explainable).
Revenue (R² 0.33) and recovery (R² 0.27–0.40) are noisy, so every prediction carries a P10–P90 range
(78–80 % coverage on held-out data) and an "insufficient history" warning when few cases match.
**Fallback:** with the models unavailable, cohort statistics (median and P10/P90 of the most similar cases).

## 7. Safety Around Synapt

- `trident_cypher` is not tenant-scoped server-side → only six fixed, provider-pinned templates are sent.
- PII masking turns regions into `[LOCATION_x]` tokens → a region bridge maps them back.
- Feedback is written to Synapt only as a verdict on the app's own `query_id`.

## 8. Summary of Architecture Trade-Offs

| Decision | Benefit | Cost accepted |
|---|---|---|
| Synapt as knowledge substrate | Graph reasoning, playbooks, memory, quality signals | Network dependency (mitigated by fallbacks) |
| Dual persistence | Full-dataset ML + cheap ingestion | Two stores joined by ID |
| LangGraph StateGraph | Auditable, parallel, streamable | Less agent autonomy |
| RRF fusion | No score calibration | Ignores score magnitude |
| Quantile ranges | Honest uncertainty | 2 extra models per target |
| Fixed Cypher templates | No cross-tenant reads | Less flexible analytics |
| SQLite for operational state | Zero-ops | Single-instance only (swap for Postgres to scale) |
