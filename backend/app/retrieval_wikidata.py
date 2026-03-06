"""
Wikidata retrieval module (no API key, no Playwright).

Fetches structured facts from Wikidata via public APIs:
- wbsearchentities: search for entity by claim text
- EntityData/<QID>.json: get entity claims and labels
- wbgetentities: resolve referenced entity labels for readable snippets

Returns evidence dicts compatible with Evidence model: source, source_url, snippet, retrieval_score.
"""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)

WIKIDATA_SEARCH_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY_DATA_URL = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
WIKIDATA_GET_ENTITIES_URL = "https://www.wikidata.org/w/api.php"
REQUEST_TIMEOUT = 10.0

# Required by Wikimedia: identify the client to avoid 403 Forbidden
WIKIMEDIA_HEADERS = {
    "User-Agent": "SelfCorrectingAI/1.0 (Academic project; contact: divyadeep@gmail.com)",
    "Accept": "application/json",
}

# Property IDs we care about for snippet building (label -> P-id)
PROPERTY_IDS = {
    "instance_of": "P31",
    "subclass_of": "P279",
    "creator": "P170",
    "developer": "P178",
    "inception": "P571",
    "field": "P101",
    "country": "P17",
    "discoverer": "P61",
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
    # Heuristic: take first phrase (before common verbs or punctuation)
    for sep in [" was ", " is ", " are ", " has ", " have ", " were ", ".", ","]:
        if sep in text:
            part = text.split(sep)[0].strip()
            if len(part) >= 2:
                return part
    # Fallback: first 2–5 words
    words = text.split()
    if len(words) <= 5:
        return text
    return " ".join(words[:4])


def _search_entity(search_term: str) -> str | None:
    """Return first Wikidata entity ID (Q-number) for search term, or None."""
    if not search_term:
        return None
    params = {
        "action": "wbsearchentities",
        "search": search_term,
        "language": "en",
        "format": "json",
    }
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.get(WIKIDATA_SEARCH_URL, params=params, headers=WIKIMEDIA_HEADERS)
            if r.status_code != 200:
                logger.warning("Wikidata search failed for %s: status %s", search_term[:50], r.status_code)
                return None
            data = r.json()
    except Exception as e:
        logger.warning("Wikidata search failed for %s: %s", search_term[:50], e)
        return None
    search_result = data.get("search") or []
    if not search_result:
        return None
    first = search_result[0]
    return first.get("id")  # e.g. "Q2407"


def _fetch_entity_data(qid: str) -> dict[str, Any] | None:
    """Fetch entity JSON from Special:EntityData. Returns entity dict or None."""
    if not qid or not qid.startswith("Q"):
        return None
    url = WIKIDATA_ENTITY_DATA_URL.format(qid=qid)
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.get(url, headers=WIKIMEDIA_HEADERS)
            if r.status_code != 200:
                logger.warning("Wikidata EntityData fetch failed for %s: status %s", qid, r.status_code)
                return None
            data = r.json()
    except Exception as e:
        logger.warning("Wikidata EntityData fetch failed for %s: %s", qid, e)
        return None
    entities = data.get("entities") or {}
    return entities.get(qid)


def _get_entity_labels(qids: list[str]) -> dict[str, str]:
    """Resolve QIDs to English labels via wbgetentities."""
    if not qids:
        return {}
    qids = [q for q in qids if q and q.startswith("Q")][:20]
    if not qids:
        return {}
    params = {
        "action": "wbgetentities",
        "ids": "|".join(qids),
        "props": "labels",
        "languages": "en",
        "format": "json",
    }
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.get(WIKIDATA_GET_ENTITIES_URL, params=params, headers=WIKIMEDIA_HEADERS)
            if r.status_code != 200:
                logger.warning("Wikidata wbgetentities failed: status %s", r.status_code)
                return {}
            data = r.json()
    except Exception as e:
        logger.warning("Wikidata wbgetentities failed: %s", e)
        return {}
    entities = data.get("entities") or {}
    labels = {}
    for eid, ent in entities.items():
        if ent.get("missing") == "":
            continue
        lb = (ent.get("labels") or {}).get("en")
        if lb and isinstance(lb.get("value"), str):
            labels[eid] = lb["value"]
    return labels


def _get_claim_value_ids(entity_data: dict[str, Any]) -> list[str]:
    """Collect referenced entity IDs from claims (for label resolution)."""
    qids = []
    claims = entity_data.get("claims") or {}
    for pid in (PROPERTY_IDS.get("instance_of"), PROPERTY_IDS.get("creator"), PROPERTY_IDS.get("developer"), "P31", "P170", "P178"):
        for claim in claims.get(pid) or []:
            snak = claim.get("mainsnak") or {}
            if snak.get("snaktype") != "value":
                continue
            dv = (snak.get("datavalue") or {}).get("value")
            if isinstance(dv, dict) and dv.get("entity-type") == "item":
                eid = dv.get("id")
                if eid:
                    qids.append(eid)
    return qids


def _format_claim_value(value: Any, labels: dict[str, str]) -> str:
    """Turn a claim datavalue into a short string."""
    if value is None:
        return ""
    if isinstance(value, dict):
        if value.get("entity-type") == "item":
            eid = value.get("id") or ""
            return labels.get(eid) or eid
        if "time" in value:
            t = value.get("time", "")
            # ISO-ish: +2020-01-01T00:00:00Z -> 2020
            m = re.search(r"([+-]?\d{4})", t)
            return m.group(1) if m else t[:10]
        if "text" in value:
            return value.get("text", {}).get("text") or ""
    return str(value)[:80]


def _build_snippet(entity_data: dict[str, Any], labels: dict[str, str], main_qid: str) -> str:
    """Build a short natural-language snippet from entity data."""
    parts = []
    en_label = (entity_data.get("labels") or {}).get("en", {}).get("value")
    if en_label:
        parts.append(en_label)
    claims = entity_data.get("claims") or {}
    # Instance of
    for claim in claims.get(PROPERTY_IDS["instance_of"]) or []:
        v = _format_claim_value((claim.get("mainsnak") or {}).get("datavalue", {}).get("value"), labels)
        if v:
            parts.append(f"Instance of: {v}.")
            break
    # Creator / developer
    for pid in (PROPERTY_IDS["creator"], PROPERTY_IDS["developer"]):
        for claim in claims.get(pid) or []:
            v = _format_claim_value((claim.get("mainsnak") or {}).get("datavalue", {}).get("value"), labels)
            if v:
                prop_name = "Created by" if pid == PROPERTY_IDS["creator"] else "Developer"
                parts.append(f"{prop_name}: {v}.")
                break
    # Inception (year)
    for claim in claims.get(PROPERTY_IDS["inception"]) or []:
        v = _format_claim_value((claim.get("mainsnak") or {}).get("datavalue", {}).get("value"), labels)
        if v:
            parts.append(f"Inception: {v}.")
            break
    if not parts:
        return en_label or main_qid
    return " ".join(parts).strip()


def retrieve_wikidata_evidence(claim_text: str) -> list[dict[str, Any]]:
    """
    Retrieve evidence snippets from Wikidata for a claim (no API key, HTTP only).

    Returns list of dicts with keys: source, source_url, snippet, retrieval_score.
    """
    search_query = _extract_search_query(claim_text)
    if not search_query:
        return []
    qid = _search_entity(search_query)
    if not qid:
        return []
    entity_data = _fetch_entity_data(qid)
    if not entity_data:
        return []
    value_qids = _get_claim_value_ids(entity_data)
    labels = _get_entity_labels([qid] + value_qids)
    snippet = _build_snippet(entity_data, labels, qid)
    if not snippet:
        return []
    source_url = f"https://www.wikidata.org/wiki/{qid}"
    return [
        {
            "source": "wikidata",
            "source_url": source_url,
            "snippet": snippet,
            "retrieval_score": 0.9,
        }
    ]
