"""
Chunk scraped page text into ~300–500 token segments for NLI.
Reuses the same logic as internal knowledge_base chunking.
"""
from . import config as _config


def chunk_text(
    text: str,
    *,
    chunk_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[str]:
    """
    Split text into overlapping word-based chunks (approximate tokens).
    """
    chunk_tokens = chunk_tokens or _config.EXTERNAL_CHUNK_TOKENS
    overlap_tokens = overlap_tokens or _config.EXTERNAL_CHUNK_OVERLAP
    tokens = (text or "").split()
    if not tokens:
        return []
    if chunk_tokens <= 0:
        return [" ".join(tokens)]
    overlap_tokens = max(0, min(overlap_tokens, chunk_tokens - 1)) if chunk_tokens > 1 else 0
    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(len(tokens), start + chunk_tokens)
        chunk = " ".join(tokens[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(tokens):
            break
        start = end - overlap_tokens
    return chunks
