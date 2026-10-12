# Architectural Design Decisions & Trade-Off Analysis

## Executive Summary

The assistant splits work by what each engine is good at: **Synapt** holds the organisational knowledge
(cases, playbooks, graph, graph-RAG answers, episodic memory) and finds the precedents for every estimate,
**precedent statistics** over the full case history produce every number (no trained model), rules
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

**Measured:** Synapt's semantic leg finds the right disruption type 87 % of the time in the top 8 (25 golden
cases).

### Requiring Synapt: one operating mode
The app runs in a single mode, on Synapt; there is no local or degraded mode (see `visual/synapt-mode.html`).
- **Benefit:** one code path is simpler to build, test and explain; every answer comes from the same engines,
  so results are consistent; and there is no silent drop in quality. A Synapt failure surfaces as a clear error
  (start-up stage `error` and 503 on data endpoints; 502 on `/api/ask` and `/api/synapt/*`; an error event on
  analyses), and `/api/health` names the last failed tool and error.
- **Trade-off:** a hard dependency on a beta network service. If Synapt is down or misconfigured, the app is
  unavailable for analysis until it recovers; each call has a timeout, so failures are fast rather than hung.

## 2. Storage Architecture: Hybrid Dual-Persistence (Synapt + Local Store)

### The Trade-Off
Ingesting 100,000 long narratives into Synapt is slow and costly, but the precedent statistics need
every row.

### The Solution: Hybrid Dual-Persistence
- **Synapt:** 4,000 case narratives, profiles and statistics over all 100k rows, 6 SOP playbooks, tickets.
- **Local:** all 100k rows in memory (BM25 + vectorised profile matching), SQLite for operational state.
- Every Synapt hit is joined back to its CSV row by `DIS-` ID, so the two stores never disagree on facts.
- The profile leg over all 100k rows raised exact-profile matches from 14 % to 83 %.

## 3. Reasoning & LLM Strategy: Synapt Reasons, the LLM Only Judges

- Following the reference capstone, no agent calls an external LLM. Classification uses vocabulary-constrained
  keyword rules (98/98 fields on the golden set), the plan comes from strategy statistics plus the Synapt
  playbook steps, the briefing is built from the evidence plus Synapt's graph-RAG answer, and `/ask` returns
  Synapt's `trident_query` answer.
- Numbers come from comparable past cases (cohort median and P10–P90, cross-checked against Synapt's nearest precedents); a deterministic fact-check
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

### Why a Supervisor with Goal-Driven Agents Was Chosen
- **Agents decide locally, the supervisor decides globally.** Each agent (`agents/base.py`) has a goal, tools
  and its own perceive → decide → act → observe loop; it checks its own work (the case-search agent widens its
  search until the evidence is good, the Report agent rewrites until the fact-check passes, the Impact agent
  cross-checks its cohort estimate against the past cases Synapt finds) and reports a message with status, confidence and requests.
- **Supervisor = goals × dependencies × requests** (`agents/supervisor.py`), not a fixed order: every goal
  whose inputs are ready runs, in parallel (case search, Synapt and impact start together), and requests
  such as the Judge's "consistency is weak, re-plan without the current primary" re-open exactly the
  dependent goals.
- **Bounded:** budgets on every loop (search ≤ 3 strategies, rewrites ≤ 2, one Judge revision, 25 supervisor
  decisions), so latency and behaviour stay predictable.
- **Conditional edge:** invalid input (guardrail violation) goes straight to END before any model call.
- **Streaming:** `route`, `agent_start`, `agent_step` and `agent_done` events (`stream_mode="custom"`).
- **Trade-off:** the agents' policies are rules written by us, not an LLM planner. That is deliberate: the
  behaviour is reproducible, testable (`tests/test_supervisor.py`) and costs nothing per run, and the agents
  still adapt to what they observe instead of following one path.

## 5. Retrieval Fusion: Reciprocal Rank Fusion vs. Weighted Scores

Cosine similarities, BM25 scores and profile scores live on different scales. RRF (k = 60) fuses by rank,
needs no calibration, and rewards agreement between legs. **Trade-off:** it ignores score magnitude.

## 6. Prediction: Precedent Statistics Instead of a Trained Model

**Decision:** no ML model. The Impact agent asks Synapt for the nearest past cases, and the estimate is the
median and P10–P90 of the closest cohort of past cases (≥ 30 cases; attributes dropped least telling first).
**Why:** every number traces back to real cases an operator can open, there is nothing to train, version or
drift, and new outcomes count the moment they are reported.
**Cost, measured on 19,921 held-out cases:** impact R² 0.68 vs 0.70, full recovery 0.35 vs 0.40, revenue
0.33 vs 0.33, risk AUC 0.87 vs 0.87 for the gradient-boosting models it replaced; P10–P90 coverage 77–79 %.
**Why Synapt's neighbours are not the estimate on their own:** on 40 held-out cases they were less accurate
(recovery MAE 35 d vs 25 d) and blending did not help, so Synapt supplies the precedents and the
cross-check, and the cohort the numbers. Counterfactuals compare two cohorts that differ only in the lever
(≥ 100 cases each side); with less history the answer widens and an "insufficient history" warning shows.

## 7. Safety Around Synapt

- `trident_cypher` is not tenant-scoped server-side → only six fixed, provider-pinned templates are sent.
- PII masking turns regions into `[LOCATION_x]` tokens → a region bridge maps them back.
- Feedback is written to Synapt only as a verdict on the app's own `query_id`.

## 8. Summary of Architecture Trade-Offs

| Decision | Benefit | Cost accepted |
|---|---|---|
| Synapt as knowledge substrate | Graph reasoning, playbooks, memory, quality signals | Network dependency on a beta service |
| Synapt required (single mode) | Simpler, consistent answers, no silent quality drop | Synapt outage = app unavailable for analysis |
| Dual persistence | Full-dataset statistics + cheap ingestion | Two stores joined by ID |
| LangGraph StateGraph | Auditable, parallel, streamable | Less agent autonomy |
| RRF fusion | No score calibration | Ignores score magnitude |
| Precedent statistics, no model | Traceable numbers, nothing to train | ~5 pts lower R² on recovery |
| Fixed Cypher templates | No cross-tenant reads | Less flexible analytics |
| SQLite for operational state | Zero-ops | Single-instance only (swap for Postgres to scale) |
