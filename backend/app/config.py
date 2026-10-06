from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


class Settings:
    SYNAPT_MCP_URL = os.getenv("SYNAPT_MCP_URL", "https://beta.synapt.ai/tristore/mcp/")
    SYNAPT_AUTH_BASE = os.getenv("SYNAPT_AUTH_BASE", "https://beta.synapt.ai/auth_service/api/v1/auth/token")
    SYNAPT_USERNAME = os.getenv("SYNAPT_USERNAME", "")
    SYNAPT_PASSWORD = os.getenv("SYNAPT_PASSWORD", "")
    SYNAPT_PROVIDER_ID = os.getenv("SYNAPT_PROVIDER_ID", "")
    SYNAPT_TOP_K = _int("SYNAPT_TOP_K", 5)
    SYNAPT_GRAPH_HOPS = _int("SYNAPT_GRAPH_HOPS", 2)

    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://aicredits.in/v1")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
    JUDGE_MODEL = os.getenv("JUDGE_MODEL", os.getenv("LLM_MODEL", "gpt-4o-mini"))

    DATA_CSV = str((BASE_DIR / os.getenv("DATA_CSV", "../supply_chain_disruption_recovery.csv")).resolve())
    ARTIFACT_DIR = BASE_DIR / "artifacts"
    FEEDBACK_DB = BASE_DIR / "artifacts" / "feedback.db"


settings = Settings()
settings.ARTIFACT_DIR.mkdir(exist_ok=True)
