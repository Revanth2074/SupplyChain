"""
Server Configuration & Path Resolver.
Centralizes filesystem locations (dataset, SQLite store, model artifacts, knowledge base,
built frontend) and the Synapt / LLM settings loaded from backend/.env.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Base directory is the service root (backend/); the repository root is one level up
BASE_DIR = Path(__file__).resolve().parent
REPO_DIR = BASE_DIR.parent
load_dotenv(BASE_DIR / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def get_base_dir() -> Path:
    return BASE_DIR


def get_dataset_path() -> str:
    """The 100,000-case Supply Chain Disruption and Recovery CSV."""
    return str((BASE_DIR / os.getenv("DATA_CSV", "../supply_chain_disruption_recovery.csv")).resolve())


def get_artifacts_dir() -> Path:
    """Runtime state: SQLite store, Synapt region tokens, evaluation results."""
    return BASE_DIR / "artifacts"


def get_db_path() -> Path:
    return get_artifacts_dir() / "feedback.db"


def get_models_dir() -> Path:
    """Trained prediction models and their validation metrics."""
    return BASE_DIR / "models"


def get_knowledge_base_dir() -> Path:
    """Markdown knowledge assets ingested into Synapt (cases, SOP playbooks, reference, tickets)."""
    return REPO_DIR / "knowledge_base"


def get_sops_dir() -> Path:
    return get_knowledge_base_dir() / "sops"


def get_documentation_dir() -> Path:
    return REPO_DIR / "documentation"


def get_frontend_dist() -> str:
    """Built React console (frontend/dist); served at / when FRONTEND_DIST is set."""
    return os.getenv("FRONTEND_DIST", "")


class Settings:
    SYNAPT_MCP_URL = os.getenv("SYNAPT_MCP_URL", "https://beta.synapt.ai/tristore/mcp/")
    SYNAPT_AUTH_BASE = os.getenv("SYNAPT_AUTH_BASE", "https://beta.synapt.ai/auth_service/api/v1/auth/token")
    SYNAPT_USERNAME = os.getenv("SYNAPT_USERNAME", "")
    SYNAPT_PASSWORD = os.getenv("SYNAPT_PASSWORD", "")
    SYNAPT_PROVIDER_ID = os.getenv("SYNAPT_PROVIDER_ID", "")
    SYNAPT_TOP_K = _int("SYNAPT_TOP_K", 5)
    SYNAPT_GRAPH_HOPS = _int("SYNAPT_GRAPH_HOPS", 2)

    # External LLM (aicredits.in) — used ONLY as the independent judge (evaluation), never in the workflow.
    # Reference-repo names first (OPENAI_*, MODEL_NAME), older LLM_* names still accepted.
    LLM_BASE_URL = os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL", "https://api.aicredits.in/v1")
    LLM_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("MODEL_NAME") or os.getenv("LLM_MODEL", "gpt-4o-mini")
    JUDGE_MODEL = os.getenv("MODEL_NAME") or os.getenv("JUDGE_MODEL") or LLM_MODEL

    DATA_CSV = get_dataset_path()
    ARTIFACT_DIR = get_artifacts_dir()
    MODELS_DIR = get_models_dir()
    FEEDBACK_DB = get_db_path()


settings = Settings()
settings.ARTIFACT_DIR.mkdir(exist_ok=True)
settings.MODELS_DIR.mkdir(exist_ok=True)
