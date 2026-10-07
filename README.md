# AI-Powered Supply Chain Disruption Assistant with Synapt

Retrieve similar historical disruptions, predict their impact, plan the response and check the answer, on top of the **Synapt context substrate** (MCP), a **FastAPI** microservice and a **React** console. It is built around the *Supply Chain Disruption and Recovery* dataset (100,000 cases).

| Layer | What it does |
|---|---|
| **Synapt (MCP)** | Semantic case retrieval, graph-RAG with a reasoning subgraph, response-playbook procedures, episodic memory, read-only graph analytics, answer-quality signals, feedback |
| **Local engine** | BM25 keyword search, ML prediction models (full 100k rows), strategy statistics, guardrails, DeepEval, LLM-as-Judge |
| **Console** | 15 pages in a sidebar grouped by stage (Detect → Investigate → Predict & explain → Decide → Act & learn), each with a plain-language *How it works* guide |

---

## What it can do

### Core (Requirement 1)
- **Hybrid search**: Synapt semantic retrieval + BM25 keyword search fused with Reciprocal Rank Fusion, with faceted filters (type, industry, tier, region, severity, backup, strategy). Falls back to local LSA search if Synapt is down (circuit breaker).
- **Classification agent**: free-text incident → structured attributes with per-field confidence (LLM + rules).
- **Guardrails**: prompt-injection defence, PII redaction, domain-relevance check, structured-field validation.
- **Prioritisation**: severity 35% / production impact 30% / financial loss 25% / risk 10% → P1–P4 with SLA.
- **Recommendations**: strategy ranking from cohort statistics + ML counterfactuals, with cited cases.

### Advanced (Requirement 2)
- **7-agent workflow** streamed over SSE: intake → investigation → impact → response planning → recovery → report → judge.
- **Prediction models** (HistGradientBoosting): production impact, revenue loss, partial/full recovery, high-impact risk, resilience score, each with **P10–P90 ranges** and an *insufficient history* warning when few past cases match.
- **Explainability**: local feature contributions and global permutation importance.
- **DeepEval** (relevancy, faithfulness, contextual relevancy, two G-Eval metrics) and **LLM-as-Judge** (6-criterion rubric).
- **Feedback loop**: ratings re-weight strategies, reported outcomes retrain the models, verdicts go back to Synapt (`trident_feedback`).

### Added in this version
| # | Feature | Where |
|---|---|---|
| 1 | **Fact-checked briefings.** The report agent receives exact figures, may not attach case IDs to the new incident, and its output is checked for unknown case IDs, placeholders, and amounts/percentages not in the evidence. One automatic rewrite on failure; result shown as a badge. | `agents.py` |
| 2 | **Synapt playbooks in the plan.** The planner fetches the matching SOP with `trident_get_procedures` and follows it; its steps appear next to the plan. | cockpit |
| 3 | **Ticket-store data.** `synapt_ingest/disruption_tickets.xlsx` (5,000 labelled tickets, `.xlsx` because the ticket gateway rejects other file types) for the console's Ticketing source, enabling mined episodes and `trident_label_ticket`. | `scripts/synapt_knowledge.py tickets` |
| 4 | **Reasoning-graph explorer.** Ask a question and see the subgraph Synapt traversed (rings = hop distance), with the answer and quality signals. | Knowledge Graph tab |
| 5 | **Ask the graph.** Six provider-scoped Cypher templates over `trident_cypher`. Free-form Cypher is not accepted because the tool is not tenant-scoped on the server. | Knowledge Graph tab |
| 6 | **Synapt quality next to DeepEval.** Per-answer knowledge / procedure / graph confidence and trust signal are logged and shown with the DeepEval scores. | Quality tab |
| 7 | **Counterfactual what-if.** "Had a backup / responded sooner / Tier 1 / different strategy" re-runs the models and shows the deltas. | Simulator, cockpit |
| 8 | **Prediction ranges.** 80% intervals from P10/P90 quantile models (about 79% empirical coverage on held-out data). | everywhere predictions appear |
| 9 | **Supplier portfolio risk.** Upload a supplier CSV; each supplier is scored against all six disruption types weighted by regional exposure → risk heatmap and ranked list. | Portfolio Risk tab |

**Supplier tiers 1–4:** the dataset contains Tier 4 suppliers (about 10% of rows); the API, classifier, simulator, search filters and portfolio all accept them.

**3D Control Tower** (landing tab, React Three Fiber, lazy-loaded): a multi-modal logistics map. Each region is an island with its supplier sites (coloured by risk index), a container port and an airport (runway, parallel taxiway, apron, cargo terminal, tower). Your plant sits on a home island with jetties and an air cargo hub. Trucks carry containers to the ports; container ships berth alongside, are turned by tugs and ride the swell; Boeing 747-400F-proportioned freighters fly complete operations (pushback, taxi, line-up, takeoff roll and rotation, climb, coordinated turns, stabilised approach on the runway centreline, flare, rollout, runway exit, taxi-in to a nose-in stand, turnaround). Hub runway and taxiway use is sequenced so aircraft never conflict; `npm run check:traffic` verifies that numerically. Choosing a disruption type halts the modes it would hit in affected regions (Port Congestion and Labor Strike stop ports and ships, Geopolitical and Natural Disaster close sea and air lanes, Cyber Attack grounds flights, Factory Incident flags the site). Switch between the Network and Hub airport views, click a site for its risk profile, and run the full agent workflow for it.

**Synapt-native labelling and episodic memory** (Knowledge Graph tab): compares how Synapt would label an incident with the app's classifier, and shows recalled episodes.

---

### Decision assistant (Detect → Investigate → Predict → Explain → Simulate → Recommend → Act → Learn)
| Page | What it answers | How |
|---|---|---|
| **Home** | What is the assistant watching, and what needs attention now? | Live counters, animated decision loop, architecture map |
| **Early Warning** | Which suppliers are becoming risky *before* anything breaks? | External signals (live GDACS feed, pasted headlines classified by the LLM, demo alerts) matched to your suppliers; early-warning score = 60% transparent likelihood heuristic (alerts, delivery, recent incidents, stock cover, dependency, regional history) + 40% ML impact; Synapt playbook per alert; alerts can be ingested into Synapt |
| **Decision Studio** | What should we do, in money and days? | Six response scenarios simulated by the ML models; loss scales with each option's effective outage; editable mitigation-cost assumptions; net benefit, ROI and the lowest total business cost |
| **Root Cause** | Why does it hurt, and what made it worse? | Propagation chain sized by predictions; contributing / protective factors from XAI and history; optional Synapt graph explanation with its confidence |
| **Supplier Network** | If this supplier goes offline, what breaks? | Sankey of supplier → product → line → customer; outage simulation using ML recovery time, stock cover and alternative sources |
| **Incident Desk** | Is the plan actually being carried out? | SLA clocks per priority, automatic escalation chains, action tracking; closing an action with its real outcome writes a training row for retraining |

Operational supplier fields (`inventory_days`, `dependency_pct`, `on_time_rate`, `recent_disruptions`, `annual_spend_usd`, `products`) are optional portfolio columns; the bundled sample uses demo values. Products, lines and order volumes in the network view are a sample bill of materials.

### Fallback Lab (test the fallbacks live)
The **Fallback Lab** page (sidebar → System) has switches that simulate an outage of one dependency at a time: **Synapt (all tools)**, **Synapt graph-RAG only**, **Synapt playbooks only**, the **LLM gateway**, the **prediction models**, and the **live hazard feed**. A switch makes that dependency fail at its lowest level (the MCP client, the LLM wrapper, the model registry, the feed fetch), so the real error handling runs. Every page then uses its fallback: local LSA search, skipped graph/playbook steps, rule classifier, template plan and briefing, heuristic judge, and **cohort statistics** in place of the models (median and P10/P90 of the most similar historical cases). Pages say when they are on a fallback, and the top bar shows **Test mode**.

**Run self-test** calls every feature once (optionally the full 7-agent workflow) and checks each answered through the engine it should, given the switches: green = normal engine, amber = fallback took over as designed, red = unexpected path or crash (with a hint, e.g. a real outage or exhausted LLM credits). Switches are global, restore themselves after 5–120 minutes, and restoring a Synapt switch resets its circuit breaker immediately. Each Synapt tool now has its own circuit breaker, so a failing graph-RAG call cannot switch off case search. Set `ENABLE_FALLBACK_LAB=0` to lock the switches on a shared deployment.

**Known Synapt limitation:** `trident_create_entity` / `trident_create_concept` fail server-side (`index_node() missing 'neo4j_id'`), and document extraction does not create the requested typed entities (an explicit ontology document, `python -m scripts.synapt_knowledge ontology`, was ingested as a workaround: it adds searchable definitions but no new typed nodes). Graph-RAG, procedures, episodes and the ticket store all work.

## Architecture

```
React console ──/api──▶ FastAPI ──▶ Synapt MCP (beta.synapt.ai)
                          │            get_chunks · query · get_procedures · episodes
                          │            cypher (scoped) · feedback · get_stats · ingest
                          ├──▶ BM25 / LSA index  (100k CSV)
                          ├──▶ ML models         (point + P10/P90 + risk)
                          ├──▶ LLM gateway       (classify, plan, report, judge, DeepEval)
                          └──▶ SQLite            (analyses, feedback, Synapt quality log)
```

See [ARCHITECTURE.md](ARCHITECTURE.md), [DESIGN.md](DESIGN.md) and the visual pages below.

### What lives in Synapt
- 4,000-case text sample (`synapt_ingest/cases_*.md`), statistics for all 100,000 cases (`aggregate_stats.md`, `profiles.md`) and six response playbooks (`response_playbooks.md`).
- BM25, the ML models and strategy statistics run over the **full 100,000 rows**; every Synapt hit is joined back to its CSV row by `DIS-` id.
- **Region masking bridge:** Synapt's PII masking rewrites supplier regions in ingested text to `[LOCATION_<hash>]` tokens. `synapt_service.regions` learns token → region from retrieved cases (seeded in `backend/artifacts/synapt_region_tokens.json`), adds the token to region mentions in queries, and restores real names in answers.


## Presentation & documentation

Open these directly in a browser (no server needed; they work offline except for the web font):

| File | What it is |
|---|---|
| [`docs/how-it-works.html`](docs/how-it-works.html) | **11-slide presentation deck** (← → to move, **F** for full screen) with animated retrieval, agent and loop visuals |
| [`docs/architecture.html`](docs/architecture.html) | System diagram, what every component does, **how Synapt works** (tri-store, graph-RAG flow), every Synapt tool used, advantages, limitations and workarounds, request lifecycle, deployment |
| [`docs/design.html`](docs/design.html) | Design principles, dataset insights (real charts), RRF demo, interactive priority and resilience calculators, model card, agent contracts, evaluation results, storage, UI, decision log |
| [`docs/synapt-modes.html`](docs/synapt-modes.html) | **With vs. without Synapt (and without the LLM)**: four operating modes, capability matrix, measured retrieval comparison, interactive circuit breaker, LLM fallbacks |
| [PANEL_PRESENTATION.md](PANEL_PRESENTATION.md) | 10-minute talk script with timings, demo steps and claims to avoid |
| [STUDY_GUIDE.md](STUDY_GUIDE.md) | Concepts in plain words, code reading order, numbers to know, 36-question mock Q&A |

## Results at a glance

| Area | Result |
|---|---|
| Prediction models (held-out 20%) | production impact R² 0.70 · full recovery R² 0.40 · revenue R² 0.33 · partial recovery R² 0.27 · risk AUC 0.87 · P10–P90 coverage 78–80% |
| Retrieval (25 golden cases, top 8) | hybrid type precision 100% · Synapt semantic leg 87% vs local LSA fallback 68.5% · profile leg raised exact-profile matches 14% → 83% |
| DeepEval (8 full-LLM golden cases) | answer relevancy 0.98 · faithfulness 0.92 · contextual relevancy 0.89 · impact correctness 0.78 · recommendation quality 0.74 |
| Checks | classification accuracy 96.9% · LLM judge 0.98 · fact-check 100% (25/25) · guardrail suite 10/10 |
| No-LLM fallback (17 cases) | rule classifier 98.5% · heuristic judge 0.87 · fact-check 100% |
| Synapt quality (25 cases) | answer confidence 0.755 · knowledge 0.89 · procedural 0.80 · graph 0.575 · flagged degraded 100% (see the known limitation above) |

The last evaluation run hit the LLM gateway's budget after 8 of 25 cases; the remaining 17 completed on the fallbacks and are reported separately (`n_llm_cases` / `n_fallback_cases` in `eval_results.json`). Re-run the full suite from the Quality page once credits are available.

---

## Quickstart

Prerequisites: Python 3.11+, Node.js 18+.

```powershell
# backend
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # then fill in Synapt + LLM credentials
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# frontend
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 3000
```

Open http://127.0.0.1:3000 (API docs at http://127.0.0.1:8000/docs). The first start trains the models (a few minutes) and caches them in `backend/artifacts/`.

### Load the Synapt knowledge layer (once per provider)
```powershell
cd backend
python -m scripts.synapt_knowledge ingest         # profiles + response playbooks
python -m scripts.synapt_knowledge learn-regions  # seed masked-region token map
python -m scripts.synapt_knowledge tickets        # writes disruption_tickets.xlsx
python -m scripts.synapt_knowledge check          # stats + masking check
```
Then, in the Synapt console, upload `synapt_ingest/disruption_tickets.xlsx` under **Data Ingestion › Ticketing** (label fields: `disruption_type`, `industry`, `supplier_region`, `response_type`, `recovery_outcome`). This is the only way to create a ticket store. Once it exists the app uses it automatically: graph answers include the ticket store (`ticket_mode=auto`) and the Knowledge Graph tab's labeller adds `trident_label_ticket` predictions for the declared label field(s). Only fields declared at upload can be predicted, so declare all five to compare every field.

> `python -m scripts.synapt_knowledge graph` writes typed entities and edges with `trident_create_entity`; at the time of writing the Synapt server rejects those calls (`index_node() missing 'neo4j_id'`), so the command stops with that error. Playbooks and profiles are ingested as documents instead.

---

## Deploy for free (Render)
One Docker container serves the UI and the API on one URL; the ML models are trained while the image builds.
Render's free web service needs no credit card and builds straight from this GitHub repo using [`render.yaml`](render.yaml).

1. Push the repo to GitHub (secrets stay out: `.env` is git-ignored).
2. Sign in at [render.com](https://render.com) with GitHub → **New → Blueprint** → pick this repository → **Connect**.
3. Render asks for the values marked `sync: false`: `APP_PASSWORD` (what people type to open the app), `SYNAPT_USERNAME`,
   `SYNAPT_PASSWORD`, `SYNAPT_PROVIDER_ID`, `LLM_API_KEY`. Copy them from `backend/.env` → **Apply**.
4. Wait for the first build (about 10 minutes), then open `https://supply-chain-assistant.onrender.com` (or the URL Render shows).

**Memory:** the full 100k-case local index needs about 960 MB RAM; the free instance has 512 MB, so `render.yaml` sets
`INDEX_SIZE=15000` (about 370 MB, self-test 9/9). Only the local keyword/LSA index is sampled; Synapt search, the profile
leg over all 100k cases, statistics and the ML models still use every row. On a host with 1 GB+ RAM, remove `INDEX_SIZE`.

**Free-tier behaviour:** the service sleeps after 15 minutes without traffic and takes about a minute to wake (open it
before a demo). The disk is not persistent, so incidents, alerts and feedback reset on restart.

Settings: `APP_PASSWORD` (login gate), `INDEX_SIZE` (local index size), `FRONTEND_DIST` (serve the built UI, set in the
Dockerfile), `CORS_ORIGINS` (only if another site must call the API), `ENABLE_FALLBACK_LAB=0` (lock the outage switches).
Any Docker host works: `docker build -t sc-assistant . && docker run -p 7860:7860 --env-file backend/.env -e APP_PASSWORD=... sc-assistant`.

*Hugging Face Spaces:* Docker Spaces now require a PRO subscription. With PRO, `deploy/hf_deploy.py <user>/<space>`
creates the Space, stores `backend/.env` values as secrets and uploads the code.

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/search`, `/api/ask`, `/api/classify`, `/api/recommend`, `/api/prioritize` | Core search, Q&A, classification, recommendation, triage |
| `POST /api/analyze`, `/api/analyze/stream` | 7-agent workflow (JSON or SSE) |
| `POST /api/predict`, `/api/explain`, `/api/whatif` | Predictions with ranges, XAI, counterfactuals |
| `POST /api/portfolio`, `GET /api/portfolio/sample` | Supplier portfolio scoring |
| `GET /api/synapt/knowledge`, `/synapt/insights/{key}`, `/synapt/procedures`, `/synapt/episodes`, `/synapt/quality`; `POST /api/synapt/graph`, `/synapt/label` | Synapt knowledge, graph, playbooks, memory, labelling, quality |
| `POST /api/judge`, `/api/evaluate`; `GET /api/evaluate/status`, `/evaluate/results` | LLM-as-Judge, DeepEval |
| `POST /api/feedback`, `GET /api/feedback/stats`, `POST /api/models/retrain` | Feedback loop |
| `GET /api/overview` | Home-page status (alerts, risks, incidents, SLA, learning) |
| `POST /api/early-warning`; `GET/POST /api/signals`, `PATCH /api/signals/{id}`, `POST /api/signals/{id}/synapt`, `POST /api/signals/fetch-live` | Early warning and external signals |
| `POST /api/decision`, `/api/rootcause`, `/api/rootcause/synapt` | Scenario comparison with ROI; root cause |
| `POST /api/network`, `/api/network/offline` | Supplier dependency graph and outage simulation |
| `GET/POST /api/incidents`, `POST /api/incidents/seed-demo`, `PATCH /api/incidents/{id}`, `POST /api/incidents/{id}/actions`, `PATCH /api/actions/{id}` | Incident desk, SLA, escalation, action tracking |
| `GET /api/fallback-lab`, `PUT /api/fallback-lab/{switch}`, `POST /api/fallback-lab/reset`, `POST /api/fallback-lab/selftest` | Simulated outages and the fallback self-test |
| `GET /api/health`, `/api/meta`, `/api/insights`, `/api/models` | System |

---

## Testing
```powershell
cd backend
.\.venv\Scripts\python -m scripts.smoke_test basic ask analyze
cd ..\frontend
npm run build
```

Evaluation suite (`backend/app/evaluation.py`): 25 golden incidents covering every disruption type, industry and region; a deterministic 10-case guardrail suite (injection, secrets, script tags, off-topic, PII redaction, valid inputs); and up to 3 low-rated feedback inputs replayed as regression cases. Rows record whether they ran on the LLM path (`llm_used`); DeepEval and judge averages use only those rows. Run it from the Quality page or `POST /api/evaluate`.

## Repository layout
```
backend/app/        main · agents · analysis · retrieval · portfolio · ml_models · evaluation · judge · faults · fallback_lab
                    decision · risk_watch · network · ops
                    synapt_client · synapt_service · feedback · guardrails · data_store · llm · config
backend/scripts/    synapt_knowledge · smoke_test · probe_synapt · discover_synapt
frontend/src/       App · api · format · guide (page guides + glossary) · index.css + theme-light.css + app-shell.css · components/ (ControlTower.jsx, logistics3d.jsx, logistics/{paths,world}.js + aircraft.jsx, Tab*.jsx, ui.jsx, WhatIfPanel.jsx)
synapt_ingest/      Synapt documents + disruption_tickets.xlsx
docs/               how-it-works.html (deck) · architecture.html · design.html · synapt-modes.html
deploy/             hf_deploy.py · SPACE_README.md   (Hugging Face Spaces, needs PRO) · render.yaml at the root (free Render deploy)
```
