"""
External retrieval layer: web search via Playwright when internal retrieval
yields < 40% supported claims. Scrapes top N pages, chunks text, re-verifies
with the same NLI pipeline, and marks evidence as external.
"""
from .config import (
    EXTERNAL_RETRIEVAL_ENABLED,
    EXTERNAL_TOP_N_PAGES,
)
from .pipeline import run_external_pipeline

__all__ = [
    "EXTERNAL_RETRIEVAL_ENABLED",
    "EXTERNAL_TOP_N_PAGES",
    "run_external_pipeline",
]
