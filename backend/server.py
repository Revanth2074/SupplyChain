"""
Supply-Chain Disruption Assistant — FastAPI Microservice Entrypoint.
Assembles modular routes, schemas and the built React console for supply-chain disruption
investigation, prediction and response planning powered by the Synapt Context Substrate.
"""

import logging
import os
import sys

from fastapi import FastAPI

# Ensure the service root (backend/) is on sys.path
base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from routes import (  # noqa: E402
    decision_router,
    evaluation_router,
    fallback_lab_router,
    feedback_router,
    health_router,
    incidents_router,
    portfolio_router,
    predict_router,
    query_router,
    search_router,
    signals_router,
    sops_router,
    stats_router,
    synapt_router,
)
from services import webapp  # noqa: E402
from services.bootstrap import startup  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="AI-Powered Supply-Chain Disruption Assistant",
    description="Synapt-powered hybrid RAG, LangGraph multi-agent analysis, impact prediction, "
                "decision support and evaluation for supply-chain disruptions",
    version="1.0.0",
)

# Password gate (APP_PASSWORD) and CORS allow-list (CORS_ORIGINS); both off in local development
webapp.install(app)

# Mount Modular API Routers under /api
app.include_router(health_router, prefix="/api")
app.include_router(query_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(predict_router, prefix="/api")
app.include_router(decision_router, prefix="/api")
app.include_router(portfolio_router, prefix="/api")
app.include_router(signals_router, prefix="/api")
app.include_router(incidents_router, prefix="/api")
app.include_router(stats_router, prefix="/api")
app.include_router(synapt_router, prefix="/api")
app.include_router(sops_router, prefix="/api")
app.include_router(feedback_router, prefix="/api")
app.include_router(evaluation_router, prefix="/api")
app.include_router(fallback_lab_router, prefix="/api")


@app.on_event("startup")
def on_startup():
    """Create the SQLite tables, then load the 100k cases and the models in the background."""
    startup()


# Built React console (FRONTEND_DIST): mounted last so /api routes win; unknown paths fall back to index.html
webapp.serve_frontend(app)

if __name__ == "__main__":
    import uvicorn
    print("[*] Starting Supply-Chain Disruption Assistant on http://127.0.0.1:8000 ...")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
