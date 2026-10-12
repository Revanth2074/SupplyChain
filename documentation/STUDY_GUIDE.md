# Study Guide: know this project end to end

Use this to prepare for the Synapt panel. It has five parts:
1. [The 60-second explanation](#1-the-60-second-explanation)
2. [Concepts in plain words](#2-concepts-in-plain-words)
3. [Read the code in this order](#3-read-the-code-in-this-order)
4. [Numbers to know cold](#4-numbers-to-know-cold)
5. [Mock Q&A: 36 likely questions](#5-mock-qa)

A suggested preparation plan is at the end.

---

## 1. The 60-second explanation

> An operations person describes a disruption in plain words. Guardrails clean the text. An intake agent turns it into structured fields. The investigator finds similar past disruptions three ways (Synapt semantic search, BM25 keyword search, and attribute matching over all 100,000 cases) and fuses them with Reciprocal Rank Fusion. In parallel, Synapt's graph-RAG walks its knowledge graph to answer "how was this resolved before" and returns the matching response playbook. Gradient-boosting models predict production impact, revenue loss and recovery time as P10–P90 ranges and explain which factors drive them. The planner ranks response strategies by how well they actually worked historically and turns the Synapt playbook steps into the action plan. The report agent builds the briefing from that evidence plus Synapt's graph-RAG answer; a deterministic fact-checker rejects any case ID or number not in the evidence; a rule-based judge scores it. No agent calls an external LLM: the aicredits.in model is used only as the independent judge in evaluation. The operator opens an incident, tracks actions against an SLA, and the real outcome flows back as training data and as feedback to Synapt.

Three sentences if you only get three:
1. **Synapt** is the knowledge (cases, graph, playbooks, memory).
2. **Local ML** is the numbers (predictions with ranges and explanations).
3. **The external LLM** only judges (evaluation), it never generates the plan, briefing or answers.

---

## 2. Concepts in plain words

| Concept | Plain explanation | Where in code |
|---|---|---|
| **Synapt / context substrate** | A managed "memory" for AI apps. Instead of one vector index, it stores knowledge chunks, a knowledge graph, procedures and episodes, all reachable through one protocol. | `synapt/synapt_connector.py`, `agents/synapt_tools.py` |
| **MCP** (Model Context Protocol) | An open standard for AI apps to call tools. Here: JSON-RPC 2.0 messages over HTTP ("Streamable HTTP"), with a session ID header and replies as JSON or SSE. | `synapt/synapt_connector.py` |
| **Tri-store** | Synapt's three linked stores: vector (chunks), graph (Neo4j entities/relations), and procedural (SOPs), plus episodic memory. | — |
| **Graph-RAG** | Retrieval-augmented generation where, after finding relevant chunks, the system walks the knowledge graph N hops from the entities mentioned (BFS) and answers from that subgraph. Gives a visible reasoning path. | `agents/synapt_tools.fetch_synapt_rag` → `trident_query` |
| **RAG** | Retrieve relevant evidence first, then answer *from that evidence*. Here Synapt's `trident_query` does retrieval + graph walk + answer generation inside Synapt. | `agents/graph.py` |
| **BM25** | Classic keyword ranking: rewards rare words that appear often in a document, normalised by length. Good for exact terms ("ransomware", "Tier 2"). | `agents/retrieval.lexical_search` |
| **RRF** (Reciprocal Rank Fusion) | Merge ranked lists by rank: each list adds w / (60 + rank). No need to make scores comparable. Items that rank well in several lists win. | `agents/retrieval.reciprocal_rank_fusion` |
| **Profile leg** | Third retrieval list: vectorised attribute match (type, industry, tier, region, size, backup, severity) across all 100k rows. | `agents/retrieval.profile_matches` |
| **Single Synapt mode** | Synapt is required; there is no local or degraded mode. Start-up connects to Synapt first and stops in an error state if it is not configured or unreachable. Every Synapt call has a timeout; a failure raises `SynaptError` and the request returns a clear error. `/api/health` shows the last failed tool and error. | `services/bootstrap.py`, `agents/synapt_tools._call` |
| **Cohort statistics** | Used for predictions when the trained model file is absent (nothing to do with Synapt): median and P10/P90 of the most similar historical cases (keys dropped least-important-first until ≥ 30 cases). | `agents/prediction._cohort` |
| **Region bridge** | Synapt masks region names as PII (`[LOCATION_ab12]`). We learn token ↔ region from known cases and translate both ways. | `agents/synapt_tools.regions` |
| **HistGradientBoosting** | Fast gradient-boosted trees in scikit-learn with native categorical support; strong default for tabular data. | `agents/prediction.py` |
| **Quantile models / P10–P90** | Extra models trained to predict the 10th and 90th percentile, giving an 80% range. | `agents/prediction.QUANTILES` |
| **Permutation importance** | Shuffle one feature and measure how much accuracy drops; a big drop means the feature matters. Global explanation. | `agents/prediction.train` |
| **Local contribution** | For one incident: prediction minus the prediction with that feature reset to a baseline value. | `agents/prediction.explain` |
| **Agent** | Here: a function with one responsibility that reads shared state and writes its output. Not an autonomous loop; a deterministic pipeline (rules, Synapt MCP calls, ML, templates); no LLM inside. | `agents/graph.py` (LangGraph `StateGraph`) |
| **SSE** (Server-Sent Events) | One-way HTTP stream from server to browser; each agent result is pushed as it finishes. | `POST /api/analyze/stream` |
| **LLM-as-Judge** | An external LLM (aicredits.in) scoring the assistant's output with a fixed rubric. Used only in evaluation (`scripts/llm_judge.py`: grounding, impact accuracy, remediation, evidence separation; `POST /api/judge`: six criteria). The live Judge agent applies the six criteria as rules. | `agents/judge.py`, `scripts/llm_judge.py` |
| **Fact-check** | Deterministic: regex-extract case IDs, amounts and percentages from the briefing; reject any not in the evidence; one rewrite. | `agents/synthesis.check_report` |
| **DeepEval** | Test framework for LLM apps. We use AnswerRelevancy, Faithfulness, ContextualRelevancy and two G-Eval rubrics. | `services/evaluation.py` |
| **G-Eval** | An LLM grades output against custom step-by-step criteria. | `services/evaluation._metrics` |
| **Guardrails** | Input checks before any model: length, injection patterns, secrets, PII redaction, domain relevance, field vocabulary. | `agents/guardrails.py` |

---

## 3. Read the code in this order

Spend the most time on items 1–6; they are what the panel will ask about.

| # | File | What to understand |
|:-:|---|---|
| 1 | `backend/agents/graph.py` + `state.py` | The LangGraph `StateGraph`: nodes, the parallel fan-out (hybrid retriever ∥ Synapt worker), the join, streaming events |
| 2 | `backend/agents/synapt_tools.py` | `get_synapt_connector()`, timed calls + `SynaptError`, region bridge, `get_chunks`, `fetch_synapt_rag` (graph-RAG + quality), `fetch_synapt_procedures`, `search_nodes`, `synapt_worker_node` |
| 3 | `backend/synapt/synapt_connector.py` | `SynaptConfig`, `SynaptMCPConnector`: authenticate → `initialize_mcp` → `call_tool` (schema-driven argument injection, SSE parsing, re-auth on 401) |
| 4 | `backend/agents/retrieval.py` | `lexical_search`, `semantic_search_synapt`, `reciprocal_rank_fusion`, `hybrid_search` (three legs + rerank), `profile_matches` |
| 5 | `backend/agents/prediction.py` | Features, targets, `train`, quantiles, `predict` (ranges, support), cohort-statistics fallback, `explain`, `whatif`, `resilience` |
| 6 | `backend/agents/classifier.py`, `impact_analysis.py`, `planner.py` | Classification (vocabulary-constrained rules), P1–P4 priority, strategy effectiveness + plan with Synapt playbook steps |
| 7 | `backend/agents/synthesis.py`, `judge.py` | Briefing + deterministic fact-check with one rewrite; 6-criterion judge + heuristic fallback |
| 8 | `backend/agents/guardrails.py` | Patterns and why each exists; `guardrails_node` routes invalid input straight to END |
| 9 | `backend/services/decision.py`, `risk_watch.py`, `ops.py` | Scenario money model, early-warning heuristic, SLA/escalation/actions |
| 10 | `backend/services/feedback.py`, `evaluation.py` | Strategy boosts (×0.85–1.15), outcomes → retraining, golden set |
| 11 | `backend/server.py` + `routes/` + `schemas/` | How the 14 routers mount under `/api`; know `/api/analyze/stream`, `/api/search`, `/api/predict`, `/api/health` |
| 12 | `backend/scripts/build_knowledge_base.py`, `synapt/ingest_to_synapt.py`, `synapt/test_connection.py` | How the knowledge base is generated, loaded into Synapt and verified |
| 13 | `backend/static/index.html`, `app.js` | The console: 11 views grouped by stage (incl. the 3D Control Tower and History), one loader per view, `track()` history logging, the SSE stream reader for the 7 agents |

Exercise: run one incident in the cockpit, open the browser dev tools Network tab, and match each SSE event to the agent code that produced it.

---

## 4. Numbers to know cold

**Data**
- 100,000 cases; 6 disruption types, 5 industries, 5 regions, tiers 1–4, severity 1–5, 5 response strategies.
- Severity 1 → 5: full recovery 30 → 152 days; production impact 13% → 62%; loss $1.1M → $5.1M.
- Backup supplier: full recovery 90 → 64 days (≈ 26 days saved).
- Fastest strategy on average: Alternative Supplier (63 d); slowest: Combined Strategy (108 d, used on harder cases).
- Supplier size drives loss: Large $6.3M, Medium $1.8M, Small $0.5M.

**Synapt content**
- 43 Markdown files: 4,000 case narratives, profiles for all 100k, aggregate stats. 6 playbooks. 5,000 tickets (`.xlsx`). 15 MCP tools wired in.

**Retrieval**
- RRF k = 60; semantic weight 0.6, keyword 0.4, profile 0.6; final rank = 0.5 fused + 0.5 similarity.
- Profile leg: exact-profile matches 14% → 83%.
- Synapt semantic leg alone (25 golden cases, top 8): type precision **87%**, similarity 0.78; full hybrid 100%.

**Models** (held-out 20%)
| Target | Metric |
|---|---|
| Production impact | R² 0.70, MAE 7.8 pts |
| Revenue loss | R² 0.33, MAE $1.59M |
| Full recovery | R² 0.40, MAE 31 d |
| Partial recovery | R² 0.27, MAE 15 d |
| High-impact risk | AUC 0.87 |
| P10–P90 coverage | 78–80% (target 80%) |

**Formulas**
- Priority = 0.35 severity + 0.30 impact + 0.25 loss (log scale, $10k–$50M) + 0.10 risk → P1 ≥ 70, P2 ≥ 50, P3 ≥ 30, else P4.
- SLA: P1 4 h, P2 24 h, P3 72 h, P4 168 h.
- Strategy effectiveness = (0.35 full + 0.25 predicted + 0.25 loss + 0.15 partial) × confidence × feedback boost.
- Feedback boost = 1 + 0.15 × mean((rating − 3)/2) × min(1, n/3) → ×0.85…1.15.
- Early warning = 60% likelihood (signals) + 40% ML impact. A heuristic, because the dataset has no time dimension.
- Resilience = backup 25 + tier ≤15 + size ≤15 + recovery speed ≤25 + impact absorption ≤20.

**Evaluation** (`backend/artifacts/eval_results.json`; 25 golden cases + 10 guardrail cases)
- All 25 analyses ran to completion with no LLM. The judge gateway ran out of credits after 16 cases, so DeepEval and the LLM judge cover **16**; the analyses themselves were unaffected, which is the point of keeping the LLM out of the workflow.
- DeepEval (16): answer relevancy **0.985**, faithfulness **0.90**, contextual relevancy **0.88**, impact correctness **0.75**, recommendation quality **0.75**.
- Independent LLM-as-Judge benchmark (`scripts/llm_judge.py`, 10 cases): **9/10 pass**, grounding **0.98**, impact accuracy **1.00**, remediation **1.00**, evidence separation **0.975**. The one fail is Synapt's own answer naming a strategy not in its returned chunks.
- Rule classification **100%** (98/98 fields). Fact-check pass rate **100%** (all 25). Rule audit **0.90**. Guardrail suite **10/10**. Retrieval type precision **98%**. 28 pytest unit tests.
- Synapt over all 25: answer confidence **0.755**, knowledge **0.89**, procedural **0.80**, graph **0.576**, degraded flag on **100%** of answers (thin typed graph).
- Re-run the full 25 after topping up credits: Quality page → Run evaluation, or `POST /api/evaluate`.

---

## 5. Mock Q&A

### About Synapt (expect most questions here)

**Q1. Why Synapt and not just a vector database like FAISS or pgvector?**
A vector DB answers "which passages look similar". Synapt also gives a graph walk (the reasoning path), procedures (playbooks as ordered steps), episodic memory (tickets, feedback), and per-answer confidence signals, all behind one open protocol. I measured the semantic leg on its own: 87% type precision on the golden set. The graph and procedures have no local equivalent at all, which is why the app runs only on Synapt.

**Q2. Explain exactly what happens in one `trident_query` call.**
As I understand it from the tool contract and the responses: the question (with regions masked) is embedded; top-k chunks are retrieved; entities in those chunks seed the graph; Synapt walks up to `SYNAPT_GRAPH_HOPS = 2` hops (BFS); procedures and episodes are attached; the LLM inside Synapt answers from that context; the response includes the subgraph, sources and quality signals (knowledge, procedural, graph confidence, degraded flag).

**Q3. What did you ingest, and why not all 100k narratives?**
4,000 full narratives (enough for semantic recall across every type × industry × region), compact profiles for all 100k, aggregate statistics, 6 playbooks, an ontology doc, and 5,000 tickets. Ingesting 100k long narratives is slow and costly. The local BM25, the profile leg and the ML models cover every row. I tested increasing the sample; the profile leg was the bigger win (14% → 83%).

**Q4. Your eval shows every Synapt answer as "degraded". Why?**
Graph confidence averages ~0.57 because the graph has few typed entities: `trident_create_entity` and `create_concept` fail server-side with `index_node() missing 'neo4j_id'`. I worked around it with an ontology document, but that did not produce typed entities. With entity creation fixed, I expect graph confidence, and so the degraded flag, to improve. I would like to help fix it.

**Q5. How do you use `trident_cypher` safely?**
It is not tenant-scoped on the server, so free-form Cypher could read other providers' nodes. The app only sends six fixed templates, each pinned to our `provider_id`; no user text reaches Cypher.

**Q6. What is the region bridge?**
Synapt's PII masking treats region names as locations and returns `[LOCATION_hash]`. I learn token → region from chunks whose case ID I already know (the local store has the true region), save the map, mask outgoing text the same way and unmask answers. Without it, region filtering on Synapt results breaks.

**Q7. How does feedback reach Synapt, and what does Synapt do with it?**
Every user verdict calls `trident_feedback` with the query ID, verdict and score. Synapt stores it as episodic memory against that query, which can influence future retrieval and is visible in its stats. Locally the same rating re-weights strategies and low-rated inputs become regression tests.

**Q8. What would you improve in Synapt?**
(1) Fix entity creation. (2) A tenant-scoped, read-only Cypher endpoint. (3) Per-hop graph confidence, so you can see where an answer got weak. (4) Document the ticket gateway (`.xlsx` only) and the `label_ticket` JSON-string contract. (5) Optionally allow listing fields (like region) as non-PII per provider.

**Q9. What happens if Synapt is down during the demo?**
The app runs in one mode, on Synapt, so there is no silent switch to a weaker engine. If Synapt is not configured or unreachable at start-up, the boot stage becomes "error", data endpoints return 503 and the console banner shows the start-up error. If a call fails later, it raises `SynaptError`: `/api/analyze` and the stream return an error, `/api/ask` and `/api/synapt/*` return HTTP 502, and `/api/health` reports the last failed tool and error. Every call has a timeout, so nothing hangs.

**Q9b. Why not keep a local fallback?**
A local index would answer, but worse, and without the graph walk, playbooks or confidence signals; a quietly weaker answer is risky in an operational tool. A clear error is honest and easy to monitor. BM25 and the profile leg are still part of every search, as regular hybrid legs alongside Synapt, not as a replacement for it.

**Q10. Which MCP transport do you use, and how is auth handled?**
Streamable HTTP: JSON-RPC 2.0 POSTs with an `Mcp-Session-Id` header after `initialize`. Auth: email/password → bearer token from the Synapt auth service, refreshed every 50 minutes, with automatic re-auth on 401. Replies can be JSON or SSE; the client handles both.

### Retrieval

**Q11. Why RRF instead of a weighted sum of scores?**
Cosine similarities, BM25 scores and profile scores are on different scales and distributions. RRF uses rank only, so no calibration is needed, and it rewards agreement between lists.

**Q12. Why k = 60?**
It is the standard constant from the original RRF paper. It damps the difference between rank 1 and rank 2 so one list cannot dominate. I didn't tune it; the profile leg mattered far more.

**Q13. How is metadata filtering done?**
Filters apply to every leg before fusion: BM25 and profile on the local DataFrame, and Synapt hits are filtered after the region bridge maps tokens back. Results always carry `semantic_source: "synapt"`; BM25 and the profile leg add their own matches through RRF as usual.

**Q14. How do you know retrieval is good?**
Retrieval type precision (100% in hybrid on the golden set), average attribute similarity, DeepEval contextual relevancy, and Synapt's knowledge confidence per answer.

### Models and explainability

**Q15. Why gradient boosting and not a neural network?**
Tabular data, 100k rows, mostly categorical features: gradient-boosted trees are the strongest simple baseline, train in seconds, handle categoricals natively, and are easy to explain.

**Q16. Revenue R² is only 0.33. Is the model useless?**
No. It captures the main drivers (size, severity, industry), but revenue has a lot of noise the fields can't explain. That is why I show a P10–P90 range and an "insufficient history" warning rather than a single number, and why priority uses a log scale for loss.

**Q17. Disruption type has almost zero importance. Isn't that strange?**
Average recovery does differ by type (59–100 days), but type is strongly associated with severity. Once the model knows severity, type adds almost nothing. Permutation importance measures *additional* information, so it reads near zero. It's a property of this dataset, which looks synthetic.

**Q18. How are the ranges calibrated?**
Separate quantile-loss models for P10 and P90. On held-out data the true value falls inside the range 78–80% of the time, close to the 80% target.

**Q19. What does "insufficient history" mean?**
The predictor counts historical cases matching the incident on its key attributes. With few matches, it warns that the model is extrapolating.

**Q20. How does the what-if work?**
It re-runs the same models with one input changed (backup supplier, response time, tier, strategy) and shows the deltas. It shows the association the model learned, not a proven causal effect.

**Q21. How do you predict "resilience" and "risk"?**
Risk is a classifier for "high-impact" (top-quartile loss ≥ $2.49M, OR top-quartile recovery ≥ 100 days, OR ≥ 50% production impact; 47% of cases), AUC 0.87. Resilience is a transparent 0–100 score: backup, tier, size, plus predicted recovery speed and impact absorption.

### Agents and LLM

**Q22. Are these real agents?**
They are specialised steps in a deterministic pipeline, each with one responsibility and a typed output. I chose orchestration over autonomous agents for predictability and auditability in an operational setting.

**Q23. Where is the LLM used?**
Only as the independent judge, the same way the reference Synapt capstone does it: `scripts/llm_judge.py` (10 cases, 4 rubrics), `scripts/deepeval_suite.py` (DeepEval metrics) and `POST /api/judge`. Inside the workflow, classification is vocabulary-constrained rules, the plan is strategy statistics plus the Synapt playbook steps, the briefing is built from the evidence plus Synapt's graph-RAG answer, and `/ask` returns Synapt's `trident_query` answer. Synapt does the language work on its side.

**Q24. How do you stop hallucinations?**
There is no generator LLM in our code to hallucinate: every sentence of our briefing is filled from facts, cases, statistics and the Synapt playbook. The Synapt answer is shown as its own section with Synapt's quality signals. A deterministic fact-check still rejects unknown case IDs, placeholders and amounts or percentages not in the evidence, and the judge agent scores the result.

**Q25. What if the judge LLM is down?**
Nothing in the workflow changes. Only evaluation is affected: `POST /api/judge` falls back to the rule rubric and DeepEval reports the cases it could not score.

**Q26. Why stream over SSE instead of returning one response?**
A full run takes ~13 s, mostly Synapt graph-RAG time. Streaming shows each agent's result as soon as it is ready, so the operator starts reading after ~2 s.

**Q26b. Which judge model, and why keep it separate?**
Any OpenAI-compatible endpoint, set by `OPENAI_API_KEY`, `OPENAI_BASE_URL` and `MODEL_NAME`: `gpt-4o-mini` through the aicredits.in gateway, or an NVIDIA-hosted model (e.g. `nvidia/nemotron-3-super-120b-a12b` at `integrate.api.nvidia.com`; `meta/llama-3.3-70b-instruct` was retired by NVIDIA in August 2026). Swapping the judge is a config change, no code. Keeping the judge outside the pipeline means no model grades its own text, a gateway outage or budget limit cannot break an analysis, and an analysis costs no credits.

### Evaluation and quality

**Q27. What does each DeepEval metric mean?**
Answer relevancy: does the answer address the question. Faithfulness: are its claims supported by the retrieved context. Contextual relevancy: is the retrieved context relevant to the question. Recommendation quality and Impact analysis correctness are G-Eval rubrics I wrote.

**Q28. Recommendation quality is your lowest score (0.75). Why?**
The G-Eval rubric penalises any number or case ID it cannot find in the retrieval context, and asks for time-bound actions. Plans cite strategy statistics (cohort averages) that are computed, not quoted from a retrieved passage, so the evaluator can't always trace them. Fixes: put the strategy table into the retrieval context the evaluator sees, and require a deadline on every action. Faithfulness (0.90) shows the briefing itself is well grounded.

**Q29. Isn't the judge biased?**
Less than before: the LLM no longer grades its own text, because our output is built from evidence, not written by an LLM. It's still not the only check: the fact-check is deterministic, classification accuracy is exact-match against labels, and the guardrail suite is deterministic.

**Q30. How big is your evaluation set?**
25 golden incidents covering all 6 types, 5 industries and 5 regions, plus 10 guardrail cases and up to 3 replayed low-rated inputs; and a separate 10-case LLM-as-Judge benchmark. In the last run the judge's credits ran out after 16 cases, so DeepEval covers 16 while all 25 analyses completed. It's a regression suite, not a benchmark; I'd grow it from real feedback.

**Q30b. You created two Synapt providers. Which one does the app use, and why?**
`supply_chain_disruptions`, the original (set in `backend/.env`). I rebuilt the knowledge base with corrected impact bands and richer case cards in `supply_chain_disruptions_v2` and compared both on the 25 golden incidents: v2 retrieved the right disruption type slightly more often (75.1% vs 72.3%) and was faster (8.7 s vs 11.7 s), but Synapt's own confidence was lower (0.714 vs 0.736 answer, 0.559 vs 0.604 graph), because the larger graph has even more unconnected entities while entity creation is broken. All reported numbers come from the original, so I kept it; v2 is one `.env` line away (EVALUATION_REPORT §5).

**Q30c. What does Synapt's own console say about your provider?**
Context Status: 174 queries, 74.8% average confidence (platform 73.9%), 0 low-confidence answers, 95% grounded, 0% likely hallucinated. Graph Evals: 99% consistency, 99.96% provenance, 0% duplicates, but 87.9% isolated entities, so coverage is 15% — the same entity-creation bug I reported, confirmed by Synapt's own report card. The console also shows the stack behind MCP: gpt-5.4-mini as its LLM, Milvus 2.6.5 for vectors, Neo4j 5.26 for the graph (see `visual/synapt-explained.html`).

### Architecture, security, operations

**Q31. Why one microservice and not several?**
One team, one deployable, shared in-memory indexes. Modules are separated by responsibility, so splitting (for example retrieval vs. agents) later is straightforward.

**Q32. How does it scale?**
Stateless API apart from SQLite and in-memory indexes. To scale: move SQLite to Postgres, put indexes in a shared store or bake them into the image, run several replicas behind a load balancer. The LLM and Synapt calls are already I/O-bound and parallel.

**Q33. How are secrets handled?**
Environment variables only (`backend/.env`, git-ignored); credentials are never written to code or logs. Optional password gate with an HMAC cookie; CORS closed unless allow-listed.

**Q34. How does the early warning predict likelihood if there's no time data?**
It doesn't learn likelihood; it's a transparent heuristic: 60% from current signals (GDACS live feed + manual), 40% from ML impact-if-disrupted. I state that openly on the page, because the dataset has no timestamps.

**Q35. Where does the feedback loop actually change behaviour?**
Ratings change strategy ranking immediately (boost ×0.85–1.15, needs ~3 ratings for full effect). Reported outcomes are appended to training data and models retrain on demand. Low-rated inputs are replayed in the next evaluation. Verdicts go to Synapt.

**Q36. If you joined the team, what would you build next?**
(1) Help fix entity creation and re-ingest a typed supply-chain ontology, then measure graph confidence again. (2) A tenant-scoped analytics endpoint. (3) Use Synapt episodes as a real-time "what happened last time" source. (4) Ship this assistant as a reference app or template showing the full read–reason–write-back loop on Synapt.

---

## Preparation plan

| Day | Do |
|---|---|
| 1 | Read §1–§2. Run the app; run 3 incidents; watch the SSE events. |
| 2 | Read `agents/graph.py`, `agents/synapt_tools.py` and `synapt/synapt_connector.py` line by line. Draw the graph from memory. |
| 3 | Read `agents/retrieval.py`, `agents/prediction.py`, `agents/impact_analysis.py`. Recompute one priority score by hand. |
| 4 | Read the four HTML pages in `documentation/visual/`. Learn §4 by heart. |
| 5 | Answer §5 out loud without notes; time the demo (3 min). |
| 6 | Full dry run of `PRESENTATION_GUIDE.md` with a timer; rehearse the "Synapt is down" answer (Q9) and where the error shows. |
