"""
Wikipedia retrieval module (no API key, no Playwright).

Fetches short textual explanations from English Wikipedia via the public MediaWiki API:
- query list=search: find page by claim/entity
- query prop=extracts: get intro plain text

Returns evidence dicts compatible with Evidence model: source, source_url, snippet, retrieval_score.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
REQUEST_TIMEOUT = 10.0
MAX_SNIPPET_CHARS = 400

# Required by Wikimedia: identify the client to avoid 403 Forbidden
WIKIMEDIA_HEADERS = {
    "User-Agent": "SelfCorrectingAI/1.0 (Academic project; contact: divyadeep@gmail.com)",
    "Accept": "application/json",
}

# Strip these leading phrases for API search so we search by main topic only (e.g. "what is ai" -> "ai")
# Longest first so "can you explain" matches before "explain"
_QUESTION_PREFIXES = (
    "can you explain ",
    "could you explain ",
    "tell me about ",
    "what is the ",
    "what are the ",
    "how does the ",
    "how do the ",
    "what is ",
    "what are ",
    "what was ",
    "what were ",
    "what does ",
    "what do ",
    "how is ",
    "how are ",
    "how was ",
    "how were ",
    "how does ",
    "how do ",
    "how can ",
    "explain ",
    "define ",
    "describe ",
    "give me ",
    "give a ",
)


def _strip_question_prefix(text: str) -> str:
    """Remove leading question/instruction phrases; return main topic for API search."""
    t = (text or "").strip()
    if not t:
        return ""
    lower = t.lower()
    for prefix in _QUESTION_PREFIXES:
        if lower.startswith(prefix):
            t = t[len(prefix) :].strip()
            lower = t.lower()
            break
    return t


def _extract_search_query(claim_text: str) -> str:
    """Extract main heading for API search: strip 'what is' etc., then first phrase or first words."""
    text = _strip_question_prefix(claim_text or "")
    if not text:
        return ""
    for sep in [" was ", " is ", " are ", " has ", " have ", " were ", ".", ","]:
        if sep in text:
            part = text.split(sep)[0].strip()
            if len(part) >= 2:
                return part
    words = text.split()
    if len(words) <= 5:
        return text
    return " ".join(words[:4])


def _search_wikipedia(search_term: str) -> list[dict[str, Any]]:
    """Search Wikipedia; return list of { pageid, title }."""
    if not search_term:
        return []
    params = {
        "action": "query",
        "list": "search",
        "srsearch": search_term,
        "srlimit": 3,
        "format": "json",
    }
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.get(WIKIPEDIA_API_URL, params=params, headers=WIKIMEDIA_HEADERS)
            if r.status_code != 200:
                logger.warning("Wikipedia search failed for %s: status %s", search_term[:50], r.status_code)
                return []
            data = r.json()
    except Exception as e:
        logger.warning("Wikipedia search failed for %s: %s", search_term[:50], e)
        return []
    query = data.get("query") or {}
    search = query.get("search") or []
    return [{"pageid": str(s.get("pageid")), "title": (s.get("title") or "").strip()} for s in search if s.get("pageid")]


def _fetch_extract(page_id: str) -> tuple[str, str]:
    """Fetch intro extract for a page. Returns (snippet_text, page_title)."""
    if not page_id:
        return "", ""
    params = {
        "action": "query",
        "pageids": page_id,
        "prop": "extracts",
        "exintro": "1",
        "explaintext": "1",
        "exsentences": 3,
        "exchars": MAX_SNIPPET_CHARS,
        "format": "json",
    }
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.get(WIKIPEDIA_API_URL, params=params, headers=WIKIMEDIA_HEADERS)
            if r.status_code != 200:
                logger.warning("Wikipedia extract fetch failed for page %s: status %s", page_id, r.status_code)
                return "", ""
            data = r.json()
    except Exception as e:
        logger.warning("Wikipedia extract fetch failed for page %s: %s", page_id, e)
        return "", ""
    query = data.get("query") or {}
    pages = query.get("pages") or {}
    page = pages.get(page_id) or pages.get(int(page_id)) if page_id.isdigit() else {}
    if page.get("missing"):
        return "", ""
    title = (page.get("title") or "").strip()
    extract = (page.get("extract") or "").strip()
    if extract and len(extract) > MAX_SNIPPET_CHARS:
        extract = extract[:MAX_SNIPPET_CHARS].rsplit(" ", 1)[0] + "…"
    return extract, title


def retrieve_wikipedia_evidence(claim_text: str) -> list[dict[str, Any]]:
    """
    Retrieve evidence snippets from English Wikipedia (no API key, HTTP only).

    Returns list of dicts with keys: source, source_url, snippet, retrieval_score.
    """
    search_query = _extract_search_query(claim_text)
    if not search_query:
        return []
    results = _search_wikipedia(search_query)
    evidence_list: list[dict[str, Any]] = []
    seen_snippets: set[str] = set()
    for hit in results[:2]:  # Top 2 pages max
        page_id = hit.get("pageid")
        title = hit.get("title") or ""
        if not page_id:
            continue
        snippet, resolved_title = _fetch_extract(page_id)
        if not snippet or snippet in seen_snippets:
            continue
        seen_snippets.add(snippet)
        # Build URL from title
        safe_title = quote_plus(title or resolved_title)
        source_url = f"https://en.wikipedia.org/wiki/{safe_title}" if safe_title else None
        evidence_list.append({
            "source": "wikipedia",
            "source_url": source_url or f"https://en.wikipedia.org/wiki?curid={page_id}",
            "snippet": snippet,
            "retrieval_score": 0.85,
        })
    return evidence_list
