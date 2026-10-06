# AI-Powered Supply Chain Disruption Assistant with Synapt

Retrieve similar historical disruptions, predict their impact, plan the response and check the answer, on top of the **Synapt context substrate** (MCP), a **FastAPI** microservice and a **React** console. It is built around the *Supply Chain Disruption and Recovery* dataset (100,000 cases).

| Layer | What it does |
|---|---|
| **Synapt (MCP)** | Semantic case retrieval, graph-RAG with a reasoning subgraph, response-playbook procedures, episodic memory, read-only graph analytics, answer-quality signals, feedback |
| **Local engine** | BM25 keyword search, ML prediction models (full 100k rows), strategy statistics, guardrails, DeepEval, LLM-as-Judge |
| **Console** | 9 tabs in a light theme: 3D control tower, cockpit, search, triage, simulator, portfolio risk, knowledge graph, analytics, quality |

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

See [ARCHITECTURE.md](ARCHITECTURE.md), [DESIGN.md](DESIGN.md) and [PANEL_PRESENTATION.md](PANEL_PRESENTATION.md).

### What lives in Synapt
- 4,000-case text sample (`synapt_ingest/cases_*.md`), statistics for all 100,000 cases (`aggregate_stats.md`, `profiles.md`) and six response playbooks (`response_playbooks.md`).
- BM25, the ML models and strategy statistics run over the **full 100,000 rows**; every Synapt hit is joined back to its CSV row by `DIS-` id.
- **Region masking bridge:** Synapt's PII masking rewrites supplier regions in ingested text to `[LOCATION_<hash>]` tokens. `synapt_service.regions` learns token → region from retrieved cases (seeded in `backend/artifacts/synapt_region_tokens.json`), adds the token to region mentions in queries, and restores real names in answers.

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
| `GET /api/health`, `/api/meta`, `/api/insights`, `/api/models` | System |

---

## Testing
```powershell
cd backend
.\.venv\Scripts\python -m scripts.smoke_test basic ask analyze
cd ..\frontend
npm run build
```

## Repository layout
```
backend/app/        main · agents · analysis · retrieval · portfolio · ml_models · evaluation · judge
                    synapt_client · synapt_service · feedback · guardrails · data_store · llm · config
backend/scripts/    synapt_knowledge · smoke_test · probe_synapt · discover_synapt
frontend/src/       App · api · format · index.css + theme-light.css · components/ (ControlTower.jsx, logistics3d.jsx, logistics/{paths,world}.js + aircraft.jsx, Tab*.jsx, ui.jsx, WhatIfPanel.jsx)
synapt_ingest/      Synapt documents + disruption_tickets.xlsx
```
