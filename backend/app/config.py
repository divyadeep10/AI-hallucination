"""
Phase 9: Centralized configuration from environment.
Single place for env-based settings; document switching LLM providers and deployment.
"""

import os
from typing import Optional

# Load .env from project root when running from backend/ (e.g. worker, scripts)
def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        load_dotenv(os.path.join(root, ".env"))
    except ImportError:
        pass


_load_dotenv()


# --- App ---
APP_ENV: str = os.getenv("APP_ENV", "development")
BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))

# --- Database ---
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:password@localhost:5432/major_project",
)

# --- Redis / Queue ---
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
WORKFLOW_QUEUE_NAME: str = os.getenv("WORKFLOW_QUEUE_NAME", "workflows")

# --- CORS / Frontend ---
FRONTEND_ORIGIN: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

# --- LLM: OpenAI-compatible ---
OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY") or None
OPENAI_API_BASE: str = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

# --- LLM: Google Gemini ---
GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY") or None
GEMINI_API_BASE: str = os.getenv(
    "GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta"
)
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")


def get_llm_provider() -> str:
    """Return which provider will be used: 'openai' | 'gemini' | 'none'."""
    if OPENAI_API_KEY:
        return "openai"
    if GEMINI_API_KEY:
        return "gemini"
    return "none"


def require_llm() -> None:
    """Raise if no LLM provider is configured (for startup checks if desired)."""
    if get_llm_provider() == "none":
        raise RuntimeError(
            "No LLM provider configured. Set OPENAI_API_KEY or GEMINI_API_KEY. "
            "See .env.example and docs/SETUP_AND_RUN.md."
        )
