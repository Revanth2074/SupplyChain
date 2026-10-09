# 10-Minute Panel Presentation
## AI-Powered Supply-Chain Disruption Assistant, built on Synapt

Slides: open [`visual/how-it-works.html`](visual/how-it-works.html) in a browser and press **F** for full screen; use ← → to move.
Back-up pages for questions: [`visual/architecture.html`](visual/architecture.html), [`visual/design.html`](visual/design.html), [`visual/synapt-modes.html`](visual/synapt-modes.html).
Preparation and likely questions: [`STUDY_GUIDE.md`](STUDY_GUIDE.md). What to click and ask on every page: [`visual/console-cheatsheet.html`](visual/console-cheatsheet.html). Synapt in plain words: [`visual/synapt-explained.html`](visual/synapt-explained.html).

Every number in this script is real: from `backend/models/prediction_metrics.json`, `backend/artifacts/eval_results.json`, `documentation/llm_judge_benchmark_results.json`, or measured on the 25-case golden set. Do not add numbers you cannot show.

---

## Timing

| # | Slide | Time | Goal |
|:-:|---|:-:|---|
| 1 | Title | 0:00–0:40 | One sentence on what it does |
| 2 | The problem | 0:40–1:20 | The three questions from the brief |
| 3 | The loop | 1:20–2:00 | Detect → Investigate → Predict → Decide → Act → Learn |
| 4 | Synapt at the core | 2:00–2:50 | Tri-store + MCP, why it is more than a vector DB |
| 5 | Hybrid search | 2:50–3:30 | Three legs, RRF, 14% → 83% |
| 6 | Seven agents | 3:30–4:10 | One job each, streamed live |
| — | **Live demo** | 4:10–7:10 | Cockpit → Decision Studio → Incident Desk |
| 7 | Predict & explain | 7:10–7:40 | Ranges, honest R², drivers |
| 8 | Decide & act | (skip if demo covered it) | Priority, money, SLA |
| 9 | Trust | 7:40–8:30 | DeepEval + fact-check + fallback numbers |
| 10 | What I found in Synapt | 8:30–9:30 | Product feedback |
| 11 | Coverage + thanks | 9:30–10:00 | Every requirement, one image |

If time is short, drop slide 8 (the demo already shows it) and shorten slide 7.

---

## Script

### 1 · Title (40 s)
> "Supply-chain teams lose days answering three questions every time a supplier goes down. I built an assistant on Synapt that answers them in about twelve seconds, grounded in 100,000 historical disruptions. Synapt does the reasoning, ML models produce every number, every claim is checked against evidence, and no agent calls an LLM: an external model is used only to grade the output."

### 2 · The problem (40 s)
- The three questions come straight from the brief: *has this happened before and how was it resolved; what drives impact and loss; which response worked and how fast.*
- Today's failure modes: manual search, keyword search that misses meaning, gut-feel estimates, and chatbots that invent numbers.

### 3 · The loop (40 s)
- One product, six stages; the console's sidebar is organised the same way so a non-expert can follow it.
- Detect (early warning) → Investigate (cockpit, search, graph) → Predict (simulator, root cause) → Decide (decision studio, portfolio, triage) → Act (incident desk) → Learn (quality, feedback).

### 4 · Synapt at the core (50 s)
- "Synapt is the organisation's memory, not a vector index. It has four stores: knowledge chunks, a graph, procedures, and episodes."
- What I loaded: 43 Markdown files (4,000 case narratives, compact profiles of all 100,000 cases, aggregate statistics), six response playbooks as procedures, and 5,000 labelled tickets as `.xlsx`.
- I talk to it over MCP (JSON-RPC over HTTP) using 15 tools. The core path uses four: `trident_get_chunks`, `trident_query`, `trident_get_procedures`, `trident_feedback`.
- "Every answer comes back with knowledge, procedural and graph confidence. I log those next to DeepEval, so retrieval quality is measurable in production, not just in tests."

### 5 · Hybrid search (40 s)
- Three ranked lists: Synapt semantic (meaning), BM25 (exact words), and a profile match over all 100k cases (same attributes).
- Fused by **Reciprocal Rank Fusion**: score = Σ w / (60 + rank). Fusing by rank avoids calibrating scores that use different scales.
- "Adding the profile leg raised exact-profile matches in the top results from 14% to 83%."

### 6 · Seven agents (40 s)
- Intake → Investigator → Impact → Planner → Recovery → Report → Judge. Each has one job, a typed output, and a fallback.
- None of them calls an LLM: intake is vocabulary-constrained rules, the plan is strategy statistics plus the Synapt playbook steps, the briefing is built from the evidence plus Synapt's graph-RAG answer, and the judge is a six-criterion rule audit. "That is the same split the reference Synapt capstone uses: Synapt reasons, the LLM only judges."
- Synapt calls start in parallel at intake, so they overlap with the local work. A run takes ~12 s, ~10 s of it Synapt graph-RAG. Results stream over Server-Sent Events.

### Live demo (3 min)
Have the app open and **warmed up** (first request after start-up takes ~30 s while indexes build). Use the Home page's sample incident or type:

> *Ransomware attack on our Tier 2 electronics supplier in Asia-Pacific has halted their ERP and shipments. No backup supplier is qualified. Severity 4.*

1. **Incident Cockpit** → Analyse. Narrate the agents as they light up. Point at:
   - classified fields + confidence;
   - similar cases with **"via Synapt"** badges and the Synapt confidence chip;
   - P10–P90 ranges and the priority badge;
   - the plan's first actions are the Synapt playbook steps ("Step 1, Step 2 …"), and the rationale says why the top strategy beat the fastest one;
   - the briefing sections are labelled evidence / prediction / recommendation / Synapt answer;
   - the **fact-check passed** badge and the rule-audit verdict.
2. Click **What-if → add backup supplier**: recovery drops; "this is the ML model; no LLM is involved anywhere in the workflow."
3. **Decision Studio**: same incident. "Releasing the buffer is recommended: +$390k net benefit vs doing nothing, 18 days sooner. A qualified backup would be worth +$537k, which is the business case for dual-sourcing."
4. **Open incident & track actions** → Incident Desk: SLA clock, escalation chain; close an action with a real outcome → "this becomes training data and a `trident_feedback` verdict."
5. **Fallback Lab** (30 s, strong for this panel): switch **Synapt (all tools)** off → **Run self-test** → 15/15 checks still pass, amber badges show the local fallbacks. Switch it back on. Optionally switch the **LLM judge** off: nothing in the workflow changes, only grading falls back to rules. "This is the circuit breaker and fallback design, proven live rather than claimed."
6. (If time) **Knowledge Graph**: the reasoning subgraph Synapt walked.

Backup plan if the network fails: say "this is exactly the fallback case," open the Fallback Lab and run the self-test: it will show which engines are down and that every feature still answered.

### 7 · Predict & explain (30 s)
- Models: HistGradientBoosting on all 100,000 rows, 80/20 split.
- Honest numbers: production impact R² 0.70; full recovery R² 0.40; revenue R² 0.33; risk AUC 0.87.
- "That is why every prediction is a P10–P90 range. On held-out data the range contains the real value about 79% of the time, against an 80% target."
- Drivers: severity dominates; a backup supplier saves about 26 days on average (90 → 64). Disruption type matters mostly *through* severity.

### 8 · Decide & act (optional, 30 s)
- Priority = 35% severity + 30% impact + 25% loss (log scale) + 10% risk → P1–P4 with SLAs of 4 h / 24 h / 3 days / weekly.
- Decision engine compares options in money, scaled by outage days; cost assumptions are editable.

### 9 · Trust (50 s)
Read the numbers from the slide: DeepEval on 16 judged golden cases (relevancy 0.985, faithfulness 0.90, contextual relevancy 0.88, impact 0.75, recommendation 0.75); independent LLM-as-Judge benchmark 9/10 (grounding 0.98); rule classification 100%; 28 unit tests. Then the key line: "No agent calls an LLM. Synapt does the reasoning; the external model only grades. When the judge ran out of credits after 16 cases, all 25 analyses still completed, because the workflow doesn't depend on it." Then:
- Fact-check pass rate and guardrail suite: both on the slide.
- "If Synapt is down, a circuit breaker opens after three failures and search switches to a local index. On the golden set, Synapt's semantic search finds the right disruption type 87% of the time versus 68.5% for the fallback. With all three legs fused, both reach 100%, so the app degrades instead of breaking."

### 10 · What I found in Synapt (60 s): the slide that matters most to this panel
- `trident_create_entity` / `create_concept` fail with `index_node() missing 'neo4j_id'`. Few typed entities → graph confidence ~0.57, and every eval answer was flagged **degraded**. Worked around with an ontology document.
- `trident_cypher` is not tenant-scoped, so I only send six fixed templates pinned to our `provider_id`.
- PII masking turns regions into `[LOCATION_x]` tokens; I built a token ↔ region bridge.
- Ticket mining accepts `.xlsx` only, and `trident_label_ticket` needs a JSON string; both undocumented.
- Suggestion: per-hop graph-confidence breakdown and a tenant-scoped, read-only Cypher endpoint.
> "I used every part of the product, found its edges, and worked around each one without hiding it. That is how I would work on the team."

### 11 · Coverage + thanks (30 s)
- Every Requirement 1 and Requirement 2 item is delivered; all four deliverables (architecture, design, code, presentation) are in the repo.

---

## Claims to avoid
| Don't say | Say instead |
|---|---|
| "Zero hallucination" | "No generator LLM in our code; the briefing is built from evidence and fact-checked (100% on the golden set). Synapt's own answer is shown separately with its confidence" |
| "The LLM judge says it's perfect" | "An independent model passed 9 of 10 cases; the one fail was Synapt's answer naming a strategy not in its chunks" |
| "100% uptime" | "Degrades gracefully: circuit breaker + local fallback" |
| "90% faster triage", "$250B industry loss" | Nothing; there is no source |
| "R² 0.70" (alone) | "0.70 for production impact; 0.27–0.40 for recovery and revenue, so we show ranges" |
| "Synapt knows all 100k cases" | "Full narratives for 4k, compact profiles for all 100k; local search covers every row" |
| "The graph proves causality" | "The graph shows the reasoning path; the models give correlations; root-cause chains are templates filled with model outputs" |

---

## Rehearsal checklist

Run through this once the day before and once an hour before.

1. **Warm-up (5 min before):** start the backend and frontend, open the Incident Cockpit and run the sample incident once (first run builds indexes). Check the header: Synapt **Connected**, Models **Ready**.
2. **Timing pass:** read the script aloud with a timer; the live demo must fit 3:00. Cut slide 8 first, then shorten slide 7.
3. **Three answers to say without notes:**
   - *"Where is the LLM?"* Only as the independent judge: `scripts/llm_judge.py` (10 cases, 4 rubrics, 9/10 pass), DeepEval, and `POST /api/judge`. No agent calls it.
   - *"Why not let the LLM write the plan?"* An earlier version did. When the gateway ran out of credits mid-evaluation, plans silently fell back to templates. Now an analysis costs no credits, can't be broken by the gateway, and the judge never grades its own text. The cost: briefings read like structured reports rather than prose.
   - *"What did you find in Synapt?"* Slide 10, the four findings, each with its workaround.
4. **Failure drills:** pull the network cable (or switch Synapt off in the Fallback Lab) and run the demo incident: it must still finish with "via local" badges. Then switch everything back on.
5. **Numbers card** (keep on paper): DeepEval relevancy 0.985 / faithfulness 0.90 (16 judged); LLM-judge 9/10, grounding 0.98; classification 100%; fact-check 100%; guardrails 10/10; 28 unit tests; Fallback Lab 15/15 ×3; impact R² 0.70, risk AUC 0.87; Synapt semantic 87% vs 68.5% local.
6. **Reset after rehearsal:** Fallback Lab → **Restore all**, so no switch is left off for the real session.
