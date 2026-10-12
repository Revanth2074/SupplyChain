# Supply-Chain Disruption Assistant — Empirical Evaluation Benchmark Report

All figures are measured. Raw results: [`deepeval_benchmark_results.json`](deepeval_benchmark_results.json)
(snapshot of `backend/artifacts/eval_results.json`) and `backend/artifacts/precedent_validation.json`.
Re-run with `python scripts/deepeval_suite.py`, `python scripts/llm_judge.py`, `python -m pytest tests` and
`python scripts/validate_precedent.py`. The workflow under test uses no LLM; the external LLM (`gpt-4o-mini`
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
| Precedent estimates, no trained model (held-out 20 %) | Production impact R² / MAE | **0.68 / 7.9 pts** |
| | Full recovery R² / MAE | **0.35 / 31 days** |
| | Revenue loss R² | **0.33** |
| | High-impact risk AUC | **0.87** |
| | P10–P90 interval coverage | **78–80 %** (target 80 %) |
| Synapt quality signals (25 cases) | Answer / knowledge / procedural / graph confidence | **0.755 / 0.891 / 0.797 / 0.576** |

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

Same method as the reference Synapt capstone: the assistant runs **without any LLM** (rules + Synapt MCP + precedent
statistics + templates) and an external model (`gpt-4o-mini` via the aicredits.in gateway) grades each response against the
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

## 3. Impact Estimates from Precedent (no trained model)

### Method
There is no ML model. The Impact agent asks Synapt (`trident_get_chunks`) for the nearest past cases, then
estimates each outcome as the median and P10–P90 of the closest cohort of past cases (at least 30; attributes
dropped least telling first). Synapt's precedents are attached to every estimate and cross-check it.

### Splitting Integrity
Random 80/20 split with a fixed seed (the dataset has no timestamps, so a chronological split is not possible):
cohorts are built from the 80 % and each of the 19,921 held-out cases is estimated from them
(`scripts/validate_precedent.py`).

### Empirical Validation Metrics

| Target | R² / AUC | MAE | P10–P90 coverage | Gradient-boosting models it replaced |
|---|---|---|---|---|
| Production impact (%) | 0.683 | 7.93 pts | 78.9 % | 0.700 |
| Revenue loss (USD) | 0.334 | $1.58M | 77.4 % | 0.326 |
| Full recovery (days) | 0.354 | 31.0 d | 77.8 % | 0.400 |
| Partial recovery (days) | 0.174 | 15.3 d | 78.6 % | 0.274 |
| High-impact risk | AUC 0.867 | — | — | AUC 0.873 |

**Honest reading:** within 2 points on impact, revenue and risk; 5–10 points lower R² on recovery. In exchange
every number traces back to real cases, nothing is trained or versioned, and reported outcomes count at once.

### Synapt precedents vs cohort
On 40 held-out cases, the similarity-weighted median of Synapt's nearest cases alone gave impact MAE 9.9 pts
and full-recovery MAE 35 d, against 7.8 pts and 25 d for the cohort on the same cases; blending the two did not
improve the cohort. So Synapt supplies the precedents and the cross-check, the cohort the numbers. On the 25
golden incidents the Impact agent used 40 close Synapt precedents on average (minimum 5) and flagged 4 incidents
where Synapt's precedents and the cohort disagreed by more than 50 %.

### What separates outcomes
Share of outcome variance each attribute explains on its own (η²): severity dominates impact (0.57), full
recovery (0.33) and risk (0.28); supplier size (0.16) and industry (0.07) drive revenue loss; response strategy,
disruption type and backup supplier come next for recovery.

## 4. Hybrid Retrieval Architecture (Lexical + Synapt Semantic + Profile + RRF)

### Mathematical Formulation
$$\text{RRF}(d) = \sum_{m \in \{\text{Synapt semantic},\ \text{BM25},\ \text{profile}\}} \frac{w_m}{60 + \text{rank}_m(d)}, \qquad w = (0.6,\ 0.4,\ 0.6)$$
followed by a rerank: 0.5 × fused score + 0.5 × attribute similarity to the incident.

### Retrieval Channel Synergy (25 golden cases, top 8)

| Configuration | Type precision | Attribute similarity |
|---|---|---|
| Synapt semantic leg alone | 87.0 % | 0.777 |
| Full hybrid with Synapt | 100 % | 0.998 |

The profile leg raised exact-profile matches in the top results from 14 % to 83 %. The BM25 and profile legs are
regular hybrid legs, not a fallback: the app runs only on Synapt, and a Synapt failure is returned as an error.

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

## 6. Supervisor and Goal-Driven Agents

All 25 golden incidents were re-run through the supervisor and goal-driven agents (`agents/base.py`,
`agents/supervisor.py`) against live Synapt, with the runtime rule-based Judge (no LLM).

| Measure | Result |
|---|---|
| Classification (rules, 98 labelled fields) | **100 %** |
| Fact-check passed | **25 / 25** |
| Runtime Judge verdict | **25 / 25 approve** |
| Supervisor decisions per analysis | **8** (every run) |
| Average time per analysis | **12.5 s** (case search, Synapt and Impact start in parallel; Impact now asks Synapt too) |
| Agent self-corrections triggered | **0** (no widened search, Synapt re-ask, rewrite or Intake label request) |
| Impact agent flagged Synapt vs cohort disagreement | **4 / 25** (confidence lowered, message status `partial`) |

**Honest reading:** the golden descriptions are explicit, so every agent met its goal on the first try and no
self-correction was needed; the only adaptive signal was the Impact agent flagging 4 estimates its Synapt
precedents disagreed with. The adaptive behaviour is exercised elsewhere:

* a vague incident ("A fire stopped production at one of our small suppliers…") made the Intake agent ask Synapt for
  labels; the nearest cases disagreed (Electronics 43 %, Asia-Pacific 34 %), so it left those fields unknown;
* `tests/test_supervisor.py` checks the search agent widening itself when evidence is weak, keeping the best evidence
  when the goal cannot be met, the Judge routing its weakest criterion to the responsible agent, the supervisor acting
  on requests within the revision budget, dependency scheduling and the routing limit.

A golden set with deliberately vague or conflicting incidents is the next step to measure how often the agents adapt.
