# 10-Minute Panel Presentation
## AI-Powered Supply-Chain Disruption Assistant, built on Synapt

Slides: open [`docs/how-it-works.html`](docs/how-it-works.html) in a browser and press **F** for full screen; use ← → to move.
Back-up pages for questions: [`docs/architecture.html`](docs/architecture.html), [`docs/design.html`](docs/design.html), [`docs/synapt-modes.html`](docs/synapt-modes.html).
Preparation and likely questions: [`STUDY_GUIDE.md`](STUDY_GUIDE.md).

Every number in this script is real: from `backend/artifacts/models_meta.json`, `backend/artifacts/eval_results.json`, or measured on the 25-case golden set. Do not add numbers you cannot show.

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
> "Supply-chain teams lose days answering three questions every time a supplier goes down. I built an assistant on Synapt that answers them in about twenty seconds, grounded in 100,000 historical disruptions, with every number predicted by a model and every claim checked against evidence."

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
- Synapt calls start in parallel at intake, so they overlap with the local work. Results stream to the UI over Server-Sent Events.

### Live demo (3 min)
Have the app open and **warmed up** (first request after start-up takes ~30 s while indexes build). Use the Home page's sample incident or type:

> *Ransomware attack on our Tier 2 electronics supplier in Asia-Pacific has halted their ERP and shipments. No backup supplier is qualified. Severity 4.*

1. **Incident Cockpit** → Analyse. Narrate the agents as they light up. Point at:
   - classified fields + confidence;
   - similar cases with **"via Synapt"** badges and the Synapt confidence chip;
   - P10–P90 ranges and the priority badge;
   - the Synapt playbook steps next to the plan;
   - the **fact-check passed** badge and the judge verdict.
2. Click **What-if → add backup supplier**: recovery drops; "this is the model, not the LLM."
3. **Decision Studio**: same incident. "Releasing the buffer is recommended: +$390k net benefit vs doing nothing, 18 days sooner. A qualified backup would be worth +$537k, which is the business case for dual-sourcing."
4. **Open incident & track actions** → Incident Desk: SLA clock, escalation chain; close an action with a real outcome → "this becomes training data and a `trident_feedback` verdict."
5. **Fallback Lab** (30 s, strong for this panel): switch **Synapt (all tools)** off → **Run self-test** → every check still passes, amber badges show the local fallbacks. Switch it back on. "This is the circuit breaker and fallback design, proven live rather than claimed."
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
Read the DeepEval numbers from the slide (8 full-LLM golden cases: relevancy 0.98, faithfulness 0.92, contextual relevancy 0.89, impact 0.78, recommendation 0.74; judge 0.98; classification 96.9%). Be upfront: "the LLM budget ran out after 8 of 25 cases; the other 17 kept running on fallbacks, with 98.5% rule-classifier accuracy and every briefing passing fact-check, which is a live test of no-LLM mode." Then:
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
- One Docker image; deployable for free on Hugging Face Spaces behind a password.

---

## Claims to avoid
| Don't say | Say instead |
|---|---|
| "Zero hallucination" | "Fact-checked: pass rate X% on the golden set; unknown IDs and numbers are rejected and rewritten" |
| "100% uptime" | "Degrades gracefully: circuit breaker + local fallback" |
| "90% faster triage", "$250B industry loss" | Nothing; there is no source |
| "R² 0.70" (alone) | "0.70 for production impact; 0.27–0.40 for recovery and revenue, so we show ranges" |
| "Synapt knows all 100k cases" | "Full narratives for 4k, compact profiles for all 100k; local search covers every row" |
| "The graph proves causality" | "The graph shows the reasoning path; the models give correlations; root-cause chains are templates filled with model outputs" |
