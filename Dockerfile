# One container: builds the React UI, installs the FastAPI backend, trains the ML models at build time,
# and serves everything on one port. Works on Hugging Face Spaces (Docker) and any Docker host.

# ---------- 1. build the frontend
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 2. backend + built UI
FROM python:3.13-slim
# Hugging Face Spaces run containers as uid 1000
RUN useradd -m -u 1000 user
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HOME=/home/user \
    DEEPEVAL_TELEMETRY_OPT_OUT=YES ERROR_REPORTING=NO \
    FRONTEND_DIST=/app/frontend/dist PORT=7860
WORKDIR /app

COPY backend/requirements.txt backend/constraints.txt backend/
RUN pip install -r backend/requirements.txt -c backend/constraints.txt

COPY --chown=user backend/ backend/
COPY --chown=user supply_chain_disruption_recovery.csv ./
COPY --chown=user --from=web /web/dist frontend/dist
USER user

# Train once while building so the running container starts in under a minute (no .env needed here).
RUN cd backend && python -c "from app.data_store import store; from app.ml_models import registry; store.INDEX_SIZE = 1000; store.load(); registry.train()"

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health', timeout=4)"
CMD ["sh", "-c", "cd backend && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
