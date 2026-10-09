# Supply-Chain Disruption Assistant — Empirical Evaluation Benchmark Report

All figures are measured. Raw results: [`deepeval_benchmark_results.json`](deepeval_benchmark_results.json)
(snapshot of `backend/artifacts/eval_results.json`) and `backend/models/prediction_metrics.json`.
Re-run with `python scripts/deepeval_suite.py`, `python scripts/llm_judge.py`, `python -m pytest tests` and
`python scripts/train_prediction_model.py`. The workflow under test uses no LLM; the external LLM (`gpt-4o-mini`
via aicredits.in) is only the judge.

## 1. Executive Summary & Benchmark Scorecard

| Area | Metric | Result |
|---|---|---|
| DeepEval (16 of 25 golden cases judged) | Answer relevancy | **0.985** |
| | Faithfulness | **0.902** |
| | Contextual relevancy | **0.883** |
| | Impact analysis correctness (G-Eval) | **0.747** |
| | Recommendation quality (G-Eval) | **0.747** |
| LLM-as-Judge benchmark (10 cases, §2b) | Pass rate / grounding | **9/10 · 0.98** |
| Deterministic checks (25 cases) | Fact-check pass rate | **100 %** |
| | Classification accuracy (rules, no LLM) | **100 % (98/98 fields)** |
| | Runtime rule audit (6 criteria) | **0.90** |
| | Retrieval type precision (hybrid, top 8) | **98 %** |
| | Guardrail suite (10 cases) | **10 / 10** |
| | Latency per analysis (0 LLM calls) | **13.4 s** |
| Unit tests | `pytest tests` | **28 / 28** |
| Prediction models (held-out 20 %) | Production impact R² / MAE | **0.70 / 7.8 pts** |
| | Full recovery R² / MAE | **0.40 / 31 days** |
| | Revenue loss R² | **0.33** |
| | High-impact risk AUC | **0.87** |
| | P10–P90 interval coverage | **78–80 %** (target 80 %) |
| Synapt quality signals (25 cases) | Answer / knowledge / procedural / graph confidence | **0.755 / 0.891 / 0.797 / 0.576** |
| Fallback Lab self-test | All on / Synapt off / judge LLM + models + feed off | **15/15 · 15/15 · 15/15** |

## 2. DeepEval Benchmark Results

### Test Case Execution Breakdown
- **Golden set:** 25 incidents covering all 6 disruption types, 5 industries and 5 regions, with expected
  classification labels. Up to 3 low-rated operator inputs are replayed as regression cases.
- **Metrics:** AnswerRelevancy, Faithfulness and ContextualRelevancy (threshold 0.6 / 0.6 / 0.4), plus two
  G-Eval rubrics (Recommendation Quality, Impact Analysis Correctness, threshold 0.6). Judge model: `gpt-4o-mini`.
- Each row records whether the judge LLM scored it (`llm_used`); DeepEval and LLM-judge averages use only those rows.
  Deterministic metrics (classification, fact-check, rule audit, retrieval, latency) cover all 25.

### Analysis of Test Gaps & Honest Failure Audits
- **Judge credits:** the gateway returned `402 insufficient balance` after case 16 of 25. All 25 analyses still
  completed normally, because the workflow never calls the LLM (in the earlier LLM-generated design the same error
  silently switched plans and briefings to templates). DeepEval therefore covers 16 cases; top up and re-run.
- **Recommendation quality (0.75)** is the lowest score: the rubric penalises figures it cannot trace to a
  retrieved passage, and the plan cites computed cohort statistics. Fix: include the strategy table in the
  retrieval context the evaluator sees, and require a deadline on every action.
- **Classification:** the rules now get all 98 labelled fields right. Two bugs found while removing the LLM:
  "port" matched inside "export" (sanctions were read as port congestion), and "avionics electronics" was read as
  Electronics; both fixed and covered by unit tests. Vague real-world wording remains the risk for keyword rules.
- **Retrieval type precision 98 %** (was 100 %): three golden incidents (G1 Cyber Attack, G17 and G23 Factory
  Incident) each had one off-type case among the returned results (precision 0.83 each).
- **Synapt `degraded` flag on 100 % of answers:** graph confidence is low (0.575) because typed entities could
  not be created (`trident_create_entity` fails server-side with `index_node() missing 'neo4j_id'`).

## 2b. Independent LLM-as-Judge Benchmark (`scripts/llm_judge.py`)

Same method as the reference Synapt capstone: the assistant runs **without any LLM** (rules + Synapt MCP + ML +
templates) and an external model (`gpt-4o-mini` via the aicredits.in gateway) grades each response against the
grounding context it was given. Raw results: [`llm_judge_benchmark_results.json`](llm_judge_benchmark_results.json).

| Metric (10 cases: 4 incident analyses, 2 playbook questions, 2 analytics questions, 2 guardrail probes) | Result |
|---|---|
| Pass rate | **90 % (9/10)** |
| Mean grounding | **0.98** |
| Mean impact accuracy | **1.00** |
| Mean remediation correctness | **1.00** |
| Mean evidence separation | **0.975** |
| Mean latency | **11.1 s** (no LLM in the loop; Synapt graph-RAG dominates) |

- **The one failure (TC-07)** is Synapt's own graph-RAG answer to "which strategies recovered fastest for
  Natural Disaster": it named a strategy the judge could not find in the chunks returned with it (grounding 0.80).
  Our code passes that answer through unchanged, so this is reported as is.
- **What the first run taught us:** 6/10 passed. Two guardrail probes were blocked correctly, but the rubric
  only gave a correct block full marks on grounding; the rubric now scores a correct block as a pass. One
  incident (TC-03) recommended the highest-effectiveness strategy without saying why a faster one ranked lower;
  the plan rationale now explains the ranking and names the fastest strategy when it differs. Evidence
  separation rose from 0.76 to 0.975 after each briefing section was labelled (evidence / prediction /
  recommendation / Synapt answer).

## 3. Prediction Baseline (ML Model Evaluation)

### Splitting Integrity
Random 80/20 split with a fixed seed (the dataset has no timestamps, so a chronological split is not possible).

### Empirical Validation Metrics

| Target | R² / AUC | MAE | P10–P90 coverage |
|---|---|---|---|
| Production impact (%) | 0.700 | 7.79 pts | 79.6 % |
| Revenue loss (USD) | 0.326 | $1.59M | 78.8 % |
| Full recovery (days) | 0.400 | 30.95 d | 79.7 % |
| Partial recovery (days) | 0.274 | 15.25 d | 77.7 % |
| High-impact risk | AUC 0.873 | — | — |

### Feature Importance Hierarchy
Severity dominates every target. Backup supplier (full recovery), response strategy (partial recovery) and
supplier size (revenue) come next; disruption type and region add almost nothing once severity is known.

## 4. Hybrid Retrieval Architecture (Lexical + Synapt Semantic + Profile + RRF)

### Mathematical Formulation
$$\text{RRF}(d) = \sum_{m \in \{\text{Synapt semantic},\ \text{BM25},\ \text{profile}\}} \frac{w_m}{60 + \text{rank}_m(d)}, \qquad w = (0.6,\ 0.4,\ 0.6)$$
followed by a rerank: 0.5 × fused score + 0.5 × attribute similarity to the incident.

### Retrieval Channel Synergy (25 golden cases, top 8)

| Configuration | Type precision | Attribute similarity |
|---|---|---|
| Synapt semantic leg alone | 87.0 % | 0.777 |
| Local LSA leg alone (fallback) | 68.5 % | 0.725 |
| Full hybrid with Synapt | 100 % | 0.998 |
| Full hybrid without Synapt | 100 % | 0.990 |

The profile leg raised exact-profile matches in the top results from 14 % to 83 %.

## 5. Knowledge-Base Re-Ingestion: Original vs Enriched Provider

The enriched knowledge base (case cards with priority, drivers, outcome verdict and playbook link; runbook SOPs;
corrected impact bands) was ingested into a fresh provider, `supply_chain_disruptions_v2`, and compared with the
original provider on the 25 golden incidents (region masking off for both, so the queries are identical).

| Measure | Original | Enriched (v2) |
|---|---|---|
| Graph size (nodes / chunks / edges) | 894 / 688 / 1,038 | 1,568 / 1,380 / 1,935 |
| Semantic type precision (`trident_get_chunks`) | 72.3 % | **75.1 %** |
| Answer / knowledge / procedural confidence | **0.736 / 0.832 / 0.746** | 0.714 / 0.822 / 0.709 |
| Graph confidence | **0.604** | 0.559 |
| Playbook found per type (steps) | 100 % (7) | 100 % (7) |
| Answers flagged degraded | 100 % | 100 % |
| Time per query | 11.7 s | **8.7 s** |

Result: mixed. Retrieval is slightly more precise and faster, but Synapt's own confidence signals are slightly
lower, likely because the larger graph spreads relevance over more nodes while typed entities still cannot be
created (`trident_create_entity` fails server-side), so every answer stays flagged degraded. The app keeps the
original provider as default; v2 is available by setting `SYNAPT_PROVIDER_ID=supply_chain_disruptions_v2`.
