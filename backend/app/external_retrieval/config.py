"""
Configuration for the external retrieval layer (web search via Playwright).
All settings can be overridden via environment variables.
"""
import os
from typing import Optional

# Load .env from project root when running from backend/
def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        load_dotenv(os.path.join(root, ".env"))
    except Exception:
        pass


_load_dotenv()


# Enable/disable external retrieval (second layer). When true, Playwright always runs
# after internal retrieval; internal + external evidence are combined.
EXTERNAL_RETRIEVAL_ENABLED: bool = os.getenv("EXTERNAL_RETRIEVAL_ENABLED", "true").lower() in ("true", "1", "yes")

# Search engines/sources: comma-separated (tries in order until success)
# Options: google, wikipedia, duckduckgo, direct
SEARCH_SOURCES: str = os.getenv("EXTERNAL_SEARCH_SOURCES", "wikipedia,google").strip()
SEARCH_BASE_URL: str = os.getenv("EXTERNAL_SEARCH_BASE_URL", "https://www.google.com").rstrip("/")

# Number of result pages to scrape (top N)
EXTERNAL_TOP_N_PAGES: int = max(1, min(5, int(os.getenv("EXTERNAL_TOP_N_PAGES", "3"))))

# Playwright: human-like behavior
PLAYWRIGHT_HEADLESS: bool = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() in ("true", "1", "yes")
PLAYWRIGHT_TIMEOUT_MS: int = int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "30000"))
# Min/max delay (seconds) between actions to mimic human
PLAYWRIGHT_DELAY_MIN: float = float(os.getenv("PLAYWRIGHT_DELAY_MIN", "2.0"))
PLAYWRIGHT_DELAY_MAX: float = float(os.getenv("PLAYWRIGHT_DELAY_MAX", "5.0"))
# Typing delay per character (ms)
PLAYWRIGHT_TYPE_DELAY_MS: int = int(os.getenv("PLAYWRIGHT_TYPE_DELAY_MS", "80"))
# User-Agent: recent Chrome on Windows
PLAYWRIGHT_USER_AGENT: str = os.getenv(
    "PLAYWRIGHT_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)
PLAYWRIGHT_VIEWPORT_WIDTH: int = int(os.getenv("PLAYWRIGHT_VIEWPORT_WIDTH", "1920"))
PLAYWRIGHT_VIEWPORT_HEIGHT: int = int(os.getenv("PLAYWRIGHT_VIEWPORT_HEIGHT", "1080"))

# Chunking for scraped text (same as internal: ~300–500 tokens)
EXTERNAL_CHUNK_TOKENS: int = int(os.getenv("EXTERNAL_CHUNK_TOKENS", "400"))
EXTERNAL_CHUNK_OVERLAP: int = int(os.getenv("EXTERNAL_CHUNK_OVERLAP", "50"))

# Optional: proxy for Playwright (e.g. http://user:pass@host:port). Empty = no proxy.
EXTERNAL_PLAYWRIGHT_PROXY: Optional[str] = os.getenv("EXTERNAL_PLAYWRIGHT_PROXY") or None

# Block images, stylesheets, fonts to speed up and reduce fingerprint (default false)
PLAYWRIGHT_BLOCK_RESOURCES: bool = os.getenv("PLAYWRIGHT_BLOCK_RESOURCES", "false").lower() in ("true", "1", "yes")
