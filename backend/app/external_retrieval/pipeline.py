"""
External retrieval pipeline: search -> scrape top N pages -> chunk -> return evidence list.
Used when internal retrieval yields < 40% supported claims.
"""
from typing import Any

from . import config as _config
from .chunker import chunk_text
from .playwright_search import run_search_and_scrape


def run_external_pipeline(
    query: str,
    top_n_pages: int | None = None,
) -> list[dict[str, Any]]:
    """
    Run web search, scrape top N pages, chunk text, and return evidence-style dicts.
    Each item has: snippet, source_url, retrieval_score (1.0 for external), is_external=True.
    """
    if not _config.EXTERNAL_RETRIEVAL_ENABLED:
        return []
    top_n_pages = top_n_pages or _config.EXTERNAL_TOP_N_PAGES
    query = (query or "").strip()
    if not query:
        return []

    url_text_pairs = run_search_and_scrape(query, top_n=top_n_pages)
    evidence: list[dict[str, Any]] = []

    for url, raw_text in url_text_pairs:
        chunks = chunk_text(raw_text)
        for snippet in chunks:
            if len(snippet.strip()) < 50:
                continue
            evidence.append({
                "snippet": snippet.strip(),
                "source_url": url,
                "retrieval_score": 1.0,
                "is_external": True,
            })

    return evidence
