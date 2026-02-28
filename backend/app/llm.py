import json
import os
import re
from typing import Any, Optional

import httpx
from fastapi import HTTPException


class LLMProviderNotConfiguredError(Exception):
    """Raised when no LLM provider is configured via environment variables."""


async def generate_answer(prompt: str) -> str:
    """
    Generate an answer for the given prompt using the first available provider.

    Preference order:
    1. OpenAI-compatible provider if OPENAI_API_KEY is set.
    2. Gemini provider if GEMINI_API_KEY is set.
    """
    prompt = prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Query prompt must not be empty.")

    openai_api_key = os.getenv("OPENAI_API_KEY")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if openai_api_key:
        return await _generate_with_openai(prompt, openai_api_key)
    if gemini_api_key:
        return await _generate_with_gemini(prompt, gemini_api_key)
    raise LLMProviderNotConfiguredError(
        "No LLM provider configured. Set OPENAI_API_KEY or GEMINI_API_KEY in the environment."
    )


async def _generate_with_openai(prompt: str, api_key: str) -> str:
    base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant in a self-correcting multi-agent AI "
                    "system. Provide clear, factual, and concise answers suitable as "
                    "the initial draft response."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)

    if response.status_code != 200:
        msg = response.text[:500] if response.text else "No response body"
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI-compatible provider error ({response.status_code}): {msg}",
        )

    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise HTTPException(status_code=502, detail="OpenAI-compatible provider returned no choices.")

    message = choices[0].get("message") or {}
    content: Optional[str] = message.get("content")
    if not content:
        raise HTTPException(status_code=502, detail="OpenAI-compatible provider returned empty content.")

    return content.strip()


def _gemini_base_url() -> str:
    """Return Gemini API base URL, ensuring /v1beta path for generateContent."""
    base = (os.getenv("GEMINI_API_BASE") or "").strip() or "https://generativelanguage.googleapis.com"
    base = base.rstrip("/")
    if "/v1beta" not in base and "/v1" not in base:
        base = f"{base}/v1beta"
    return base


async def _generate_with_gemini(prompt: str, api_key: str) -> str:
    base_url = _gemini_base_url()
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    url = f"{base_url}/models/{model}:generateContent"
    params = {"key": api_key}
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "You are a helpful assistant in a self-correcting multi-agent AI "
                            "system. Provide clear, factual, and concise answers suitable as "
                            "the initial draft response.\n\n"
                            f"User question: {prompt}"
                        )
                    }
                ]
            }
        ]
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, params=params, json=payload)

    if response.status_code != 200:
        msg = response.text[:500] if response.text else "No response body"
        raise HTTPException(
            status_code=502,
            detail=f"Gemini provider error ({response.status_code}): {msg}",
        )

    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise HTTPException(status_code=502, detail="Gemini provider returned no candidates.")

    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    if not parts:
        raise HTTPException(status_code=502, detail="Gemini provider returned empty content.")

    text = parts[0].get("text", "")
    if not text:
        raise HTTPException(status_code=502, detail="Gemini provider returned empty text content.")

    return text.strip()


# ---------------------------------------------------------------------------
# Claim extraction (Phase 4): structured JSON output for factual claims
# ---------------------------------------------------------------------------

CLAIM_EXTRACTION_SYSTEM = """You are a claim-extraction module for a self-correcting AI system.
Your task is to extract atomic, verifiable factual claims from the given text.
Include only statements that assert facts, definitions, or cause-effect relationships.
Exclude opinions, hedges, or meta-commentary.
For each claim provide:
- claim_text: the claim in clear, normalized form (one sentence).
- entities: list of key entities (technologies, names, numbers, terms) mentioned.
- extraction_confidence: number between 0 and 1 indicating how clearly the claim is stated.
Output a single JSON array of objects with those keys. No markdown, no explanation, only the array."""


def _parse_claims_json(raw: str) -> list[dict[str, Any]]:
    """Extract a JSON array of claim objects from LLM output. Returns [] on parse failure."""
    if not raw or not raw.strip():
        return []
    text = raw.strip()
    # Remove optional markdown code fence
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        claim_text = item.get("claim_text")
        if not claim_text or not isinstance(claim_text, str):
            continue
        claim_text = claim_text.strip()
        if not claim_text:
            continue
        entities = item.get("entities")
        if not isinstance(entities, list):
            entities = []
        entities = [str(e).strip() for e in entities if e]
        confidence = item.get("extraction_confidence")
        if confidence is not None and not isinstance(confidence, (int, float)):
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = None
        if confidence is not None and (confidence < 0 or confidence > 1):
            confidence = None
        result.append({
            "claim_text": claim_text,
            "entities": entities,
            "extraction_confidence": confidence,
        })
    return result


async def extract_claims_from_text(text: str) -> list[dict[str, Any]]:
    """
    Use the configured LLM to extract factual claims from response text.

    Returns a list of dicts with keys: claim_text (str), entities (list[str]),
    extraction_confidence (float | None). Returns empty list if text is empty,
    provider is unavailable, or output is not parseable.
    """
    if not text or not text.strip():
        return []
    user_message = (
        "Extract factual claims from the following text. "
        "Output only a single JSON array of objects with keys: claim_text, entities, extraction_confidence.\n\n"
        f"Text:\n{text.strip()}"
    )
    openai_api_key = os.getenv("OPENAI_API_KEY")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    raw: Optional[str] = None
    if openai_api_key:
        raw = await _extract_claims_openai(CLAIM_EXTRACTION_SYSTEM, user_message, openai_api_key)
    elif gemini_api_key:
        raw = await _extract_claims_gemini(CLAIM_EXTRACTION_SYSTEM, user_message, gemini_api_key)
    else:
        return []
    if not raw:
        return []
    return _parse_claims_json(raw)


async def _extract_claims_openai(system: str, user: str, api_key: str) -> Optional[str]:
    base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.1,
    }
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(url, headers=headers, json=payload)
    except Exception:
        return None
    if response.status_code != 200:
        return None
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        return None
    content = (choices[0].get("message") or {}).get("content")
    return (content or "").strip() or None


async def _extract_claims_gemini(system: str, user: str, api_key: str) -> Optional[str]:
    base_url = _gemini_base_url()
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    url = f"{base_url}/models/{model}:generateContent"
    params = {"key": api_key}
    combined = f"{system}\n\n{user}"
    payload = {"contents": [{"parts": [{"text": combined}]}]}
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(url, params=params, json=payload)
    except Exception:
        return None
    if response.status_code != 200:
        return None
    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        return None
    parts = (candidates[0].get("content") or {}).get("parts") or []
    if not parts:
        return None
    return (parts[0].get("text") or "").strip() or None


# ---------------------------------------------------------------------------
# Claim verification (Phase 6): NLI-style classification via LLM
# ---------------------------------------------------------------------------

VERIFICATION_SYSTEM = """You are a fact verification module in a self-correcting AI system.
Given a CLAIM and an EVIDENCE snippet, decide whether the evidence:
- SUPPORTS the claim
- CONTRADICTS the claim
- is UNCERTAIN (related but not clearly supporting or contradicting)
- provides NO_EVIDENCE (not relevant to the claim)

Respond with a single JSON object:
{
  "status": "SUPPORTED | CONTRADICTED | UNCERTAIN | NO_EVIDENCE",
  "confidence": float between 0 and 1
}
No explanation, no extra keys, only this JSON object."""


def _parse_verification_json(raw: str) -> dict[str, Any]:
    if not raw or not raw.strip():
        return {}
    text = raw.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    status = data.get("status")
    if not isinstance(status, str) or not status.strip():
        return {}
    status = status.strip().upper()
    confidence = data.get("confidence")
    if confidence is not None and not isinstance(confidence, (int, float)):
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = None
    if confidence is not None and (confidence < 0 or confidence > 1):
        confidence = None
    return {"status": status, "confidence": confidence}


async def verify_claim_with_evidence(claim_text: str, evidence_snippet: str) -> dict[str, Any]:
    """
    Verify a claim against a single evidence snippet using the configured LLM.

    Returns a dict with keys:
    - status: 'SUPPORTED', 'CONTRADICTED', 'UNCERTAIN', or 'NO_EVIDENCE'
    - confidence: float | None

    On failure or missing provider, returns {'status': 'UNCERTAIN', 'confidence': None}.
    """
    claim = (claim_text or "").strip()
    evidence = (evidence_snippet or "").strip()
    if not claim:
        return {"status": "NO_EVIDENCE", "confidence": None}
    if not evidence:
        return {"status": "NO_EVIDENCE", "confidence": None}

    user = f"CLAIM: {claim}\nEVIDENCE: {evidence}"
    openai_api_key = os.getenv("OPENAI_API_KEY")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    raw: Optional[str] = None
    if openai_api_key:
        raw = await _verification_openai(VERIFICATION_SYSTEM, user, openai_api_key)
    elif gemini_api_key:
        raw = await _verification_gemini(VERIFICATION_SYSTEM, user, gemini_api_key)
    else:
        return {"status": "UNCERTAIN", "confidence": None}
    if not raw:
        return {"status": "UNCERTAIN", "confidence": None}

    parsed = _parse_verification_json(raw)
    status = parsed.get("status")
    confidence = parsed.get("confidence")
    if not status:
        return {"status": "UNCERTAIN", "confidence": None}

    # Use LLM labels as-is for claim-level verification (SUPPORTED = green in UI).
    # Workflow stage remains VERIFIED; per-claim status is SUPPORTED/CONTRADICTED/UNCERTAIN/NO_EVIDENCE.
    return {"status": status, "confidence": confidence}


async def _verification_openai(system: str, user: str, api_key: str) -> Optional[str]:
    base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.0,
    }
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(url, headers=headers, json=payload)
    except Exception:
        return None
    if response.status_code != 200:
        return None
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        return None
    content = (choices[0].get("message") or {}).get("content")
    return (content or "").strip() or None


async def _verification_gemini(system: str, user: str, api_key: str) -> Optional[str]:
    base_url = _gemini_base_url()
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    url = f"{base_url}/models/{model}:generateContent"
    params = {"key": api_key}
    combined = f"{system}\n\n{user}"
    payload = {"contents": [{"parts": [{"text": combined}]}]}
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(url, params=params, json=payload)
    except Exception:
        return None
    if response.status_code != 200:
        return None
    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        return None
    parts = (candidates[0].get("content") or {}).get("parts") or []
    if not parts:
        return None
    return (parts[0].get("text") or "").strip() or None

