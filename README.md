# AI-Powered Supply Chain Disruption Assistant with Synapt MCP

An enterprise-grade semantic retrieval, predictive intelligence, and multi-agent disruption response system built on the **Synapt Knowledge Substrate (MCP Connector)**, **FastAPI**, **Vite + React**, and **100,000 historical disruption records**.

---

## 🌟 Key Features

### 1. Basic Capabilities (Requirement 1)
- **Synapt MCP Knowledge Substrate**: Native Streamable HTTP MCP (JSON-RPC 2.0) connector authenticating against `https://beta.synapt.ai/auth_service` and utilizing `trident_get_chunks`, `trident_query`, `trident_search`, and `trident_feedback`.
- **Hybrid Retrieval Engine**: Reciprocal Rank Fusion (RRF) combining Synapt dense semantic retrieval with sparse BM25 keyword matching and strict faceted metadata filtering (Disruption Type, Industry, Tier 1–3, Region, Severity, Backup status).
- **Disruption Classification Agent**: Natural language incident parsing into standardized domain attributes with confidence scoring.
- **Input Validation Guardrails**: Prompt injection defense, PII redaction (email, SSN, card), and domain relevance filtering.
- **Dynamic Prioritization Matrix**: Multi-criteria weighted scoring (Severity 35%, Production Impact 30%, Financial Loss 25%, Risk 10%) mapping incidents to P1–P4 operational SLAs.

### 2. Advanced Capabilities (Requirement 2)
- **Multi-Agent Disruption Workflow (7 Agents)**:
  1. *Intake & Classification Agent*
  2. *Investigation Agent* (Synapt Graph RAG + BM25)
  3. *Impact Assessment Agent* (HistGradientBoosting ML)
  4. *Response Planning Agent* (Tactical action plan)
  5. *Recovery Analysis Agent* (Cohort percentiles P10–P90)
  6. *Report Agent* (Markdown executive briefing)
  7. *LLM-as-Judge Agent* (6-dimension rubric audit)
  *All streamed in real-time via Server-Sent Events (SSE)!*
- **Predictive ML Regressors & Classifiers**: Native categorical `HistGradientBoosting` models trained on 100,000 cases predicting:
  - Production Impact % ($R^2 \approx 0.70$)
  - Revenue Loss USD ($)
  - Full Recovery Days & Partial Recovery Days
  - High-Impact Disruption Risk Probability & Level
  - Supply Chain Resilience Score (0–100)
- **Explainable AI (XAI)**:
  - Local feature baseline delta waterfall charts
  - Global permutation feature importances across all 100k records
- **DeepEval 4.x Quality Suite**: Answer Relevancy, Faithfulness, Contextual Relevancy, GEval Recommendation Quality, and GEval Impact Analysis Correctness.
- **LLM-as-Judge**: Independent audit checking Groundedness, Relevance, Actionability, Completeness, Consistency, and Safety.
- **Continuous Improvement Loop**: Operational feedback ratings update strategy multiplier boosts, user-reported outcomes feed into active model retraining, and verdicts are synced back to Synapt MCP `trident_feedback`.
- **Executive Frontend**: Vite + React dashboard with dark glassmorphic design, Recharts interactive data visualizations, and live SSE streaming steppers.

---

## 🏗️ System Architecture

Refer to [ARCHITECTURE.md](ARCHITECTURE.md) for the complete Mermaid architectural diagram and data flow specifications.
Refer to [DESIGN.md](DESIGN.md) for detailed mathematical formulations and schemas.
Refer to [PANEL_PRESENTATION.md](PANEL_PRESENTATION.md) for the 10-minute panel presentation slide guide.

---

## 🚀 Quickstart & Execution

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm

### 1. Backend Microservice (FastAPI)
```powershell
cd d:\SupplyChain\backend
# Create virtual environment & activate
python -m venv .venv
.\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Verify .env has credentials
# (SYNAPT_MCP_URL, SYNAPT_AUTH_BASE, SYNAPT_USERNAME, SYNAPT_PASSWORD, SYNAPT_PROVIDER_ID, LLM_API_KEY, LLM_BASE_URL)

# Run server
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
- API Docs: `http://127.0.0.1:8000/docs`
- Health Check: `http://127.0.0.1:8000/api/health`

### 2. Frontend Web Application (Vite + React)
```powershell
cd d:\SupplyChain\frontend
npm install
npm run dev -- --host 127.0.0.1 --port 3000
```
- Web Application: `http://127.0.0.1:3000`

---

## 🧪 Verification & Testing

Run the automated smoke test script to test all endpoints:
```powershell
cd d:\SupplyChain\backend
.\.venv\Scripts\python -m scripts.smoke_test basic ask analyze
```

---

## 📁 Repository Structure
```
d:/SupplyChain/
├── 2026_10_05_Project 9 - AI-Powered Supply Chain Disruption Assistant with Synapt.pdf
├── supply_chain_disruption_recovery.csv (100,000 cases dataset)
├── synapt_ingest/ (Ingested case documents)
├── ARCHITECTURE.md (Deliverable 1: System architecture & Mermaid diagrams)
├── DESIGN.md (Deliverable 2: Detailed design specifications)
├── PANEL_PRESENTATION.md (Deliverable 4: 10-minute slide presentation guide)
├── README.md (Overview & quickstart)
├── backend/
│   ├── .env (Credentials & configuration)
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py (FastAPI application & endpoints)
│   │   ├── config.py (Settings & environment variables)
│   │   ├── synapt_client.py (Streamable HTTP JSON-RPC 2.0 MCP Client)
│   │   ├── synapt_service.py (Chunks, graph query, circuit breaker, feedback)
│   │   ├── data_store.py (CSV store, BM25 index, LSA index, filters)
│   │   ├── retrieval.py (Hybrid search, RRF fusion, similarity rerank)
│   │   ├── guardrails.py (Input validation, injection, PII, domain barrier)
│   │   ├── ml_models.py (HistGradientBoosting 5 targets, resilience, XAI)
│   │   ├── analysis.py (Classifier, priority formula, strategy effectiveness)
│   │   ├── agents.py (7-Agent Disruption Workflow with SSE generator)
│   │   ├── judge.py (LLM-as-Judge 6-criteria auditor)
│   │   ├── evaluation.py (DeepEval 4.x suite & golden benchmarks)
│   │   └── feedback.py (SQLite persistence, strategy boost, retraining)
│   └── scripts/
│       ├── discover_synapt.py (Tool discovery)
│       ├── probe_synapt.py (Response shape inspection)
│       └── smoke_test.py (Automated test suite)
└── frontend/
    ├── package.json
    ├── vite.config.js (Proxy /api to port 8000)
    ├── src/
    │   ├── main.jsx
    │   ├── App.jsx (Top-level layout & tab router)
    │   ├── index.css (Dark glassmorphic executive design system)
    │   ├── api.js (Client API layer with SSE reader)
    │   └── components/
    │       ├── Navbar.jsx (Status badges & tab navigation)
    │       ├── TabWorkflow.jsx (7-Agent Cockpit, briefing, action plan)
    │       ├── TabSearch.jsx (Hybrid RAG, filters & Copilot QA)
    │       ├── TabPrioritize.jsx (P1-P4 triage queue & SLAs)
    │       ├── TabPredict.jsx (What-if simulator, resilience & XAI)
    │       ├── TabAnalytics.jsx (100k cases Recharts macro intelligence)
    │       └── TabEval.jsx (DeepEval metrics & continuous learning)
```
