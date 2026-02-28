from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Any, Optional

from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.knowledge_chunk import KnowledgeChunk


EMBEDDING_MODEL_NAME = "sentence-transformers/all-mpnet-base-v2"
EMBEDDING_DIM = 768


_MODEL_LOCK = threading.Lock()
_MODEL: Optional[SentenceTransformer] = None

_BM25_LOCK = threading.Lock()
_BM25_INDEX: Optional["Bm25Index"] = None


def _default_corpus_path() -> str:
    # backend/app -> backend/
    backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(backend_root, "data", "knowledge_corpus.json")


def _simple_tokenize(text: str) -> list[str]:
    return [t for t in (text or "").lower().split() if t]


def chunk_text(text: str, *, chunk_tokens: int = 420, overlap_tokens: int = 60) -> list[str]:
    """
    Simple chunker that approximates tokens via whitespace-separated words.
    Produces ~300–500 token chunks (approx) with overlap.
    """
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


def get_embedding_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    with _MODEL_LOCK:
        if _MODEL is None:
            _MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME)
        return _MODEL


def embed_text(text: str) -> list[float]:
    """
    Embed text into a normalized vector (length EMBEDDING_DIM).
    Normalization makes cosine distance stable: cosine_similarity in [-1, 1].
    """
    t = (text or "").strip()
    if not t:
        return [0.0] * EMBEDDING_DIM
    model = get_embedding_model()
    vec = model.encode([t], normalize_embeddings=True)[0]
    return [float(x) for x in vec]


def load_corpus_documents(path: Optional[str] = None) -> list[dict[str, Any]]:
    corpus_path = path or _default_corpus_path()
    with open(corpus_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Corpus JSON must be a list of {source,text} objects.")
    docs: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip()
        if not text:
            continue
        docs.append(
            {
                "source": (item.get("source") or "").strip() or None,
                "text": text,
            }
        )
    return docs


def ingest_corpus(
    db: Session,
    *,
    corpus_path: Optional[str] = None,
    chunk_tokens: int = 420,
    overlap_tokens: int = 60,
    skip_if_exists: bool = True,
) -> int:
    """
    Ingest a curated corpus into knowledge_chunks table.
    Returns number of chunks inserted.

    Idempotency: if skip_if_exists=True and table already has rows, does nothing.
    """
    existing = db.query(KnowledgeChunk.id).limit(1).first()
    if existing and skip_if_exists:
        return 0

    docs = load_corpus_documents(corpus_path)
    inserted = 0
    for doc in docs:
        src = doc.get("source")
        for chunk in chunk_text(doc["text"], chunk_tokens=chunk_tokens, overlap_tokens=overlap_tokens):
            vec = embed_text(chunk)
            row = KnowledgeChunk(text=chunk, source=src, embedding=vec)
            db.add(row)
            inserted += 1

    db.commit()
    # BM25 index is now stale; clear it so it can be rebuilt.
    clear_bm25_cache()
    return inserted


@dataclass
class Bm25Index:
    chunk_ids: list[int]
    texts: list[str]
    bm25: BM25Okapi

    def query(self, claim: str, *, top_k: int = 20) -> dict[int, float]:
        tokens = _simple_tokenize(claim)
        if not tokens or not self.chunk_ids:
            return {}
        scores = self.bm25.get_scores(tokens)
        if scores is None:
            return {}

        # Take top_k and min-max normalize among those candidates (0..1)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[: max(1, top_k)]
        vals = [float(v) for _, v in ranked]
        smin = min(vals)
        smax = max(vals)
        denom = (smax - smin) if (smax - smin) != 0 else 1.0

        out: dict[int, float] = {}
        for idx, raw in ranked:
            norm = (float(raw) - smin) / denom
            chunk_id = self.chunk_ids[idx]
            out[chunk_id] = max(0.0, min(1.0, norm))
        return out


def clear_bm25_cache() -> None:
    global _BM25_INDEX
    with _BM25_LOCK:
        _BM25_INDEX = None


def get_bm25_index(db: Optional[Session] = None) -> Bm25Index:
    """
    Build (once) and return an in-memory BM25 index over knowledge_chunks.
    """
    global _BM25_INDEX
    if _BM25_INDEX is not None:
        return _BM25_INDEX
    with _BM25_LOCK:
        if _BM25_INDEX is not None:
            return _BM25_INDEX

        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True
        try:
            rows = db.query(KnowledgeChunk.id, KnowledgeChunk.text).order_by(KnowledgeChunk.id.asc()).all()
            chunk_ids = [int(r[0]) for r in rows]
            texts = [str(r[1] or "") for r in rows]
            tokenized = [_simple_tokenize(t) for t in texts]
            bm25 = BM25Okapi(tokenized) if tokenized else BM25Okapi([[]])
            _BM25_INDEX = Bm25Index(chunk_ids=chunk_ids, texts=texts, bm25=bm25)
            return _BM25_INDEX
        finally:
            if close_db:
                db.close()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity for normalized vectors (dot product)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(float(x) * float(y) for x, y in zip(a, b))


def embedding_search(db: Session, claim: str, *, top_k: int = 10) -> list[tuple[KnowledgeChunk, float]]:
    """
    Return top_k knowledge chunks by cosine similarity.
    Embeddings are stored as JSONB; similarity is computed in Python (no pgvector).
    Returns list of (chunk, similarity_0_to_1).
    """
    qvec = embed_text(claim)
    rows = db.query(KnowledgeChunk).all()
    scored: list[tuple[KnowledgeChunk, float]] = []
    for chunk in rows:
        emb = chunk.embedding
        if isinstance(emb, list):
            vec = [float(x) for x in emb]
        else:
            vec = []
        sim = _cosine_similarity(qvec, vec)
        sim = max(0.0, min(1.0, sim))
        scored.append((chunk, sim))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[: top_k]


def warmup_knowledge_base(*, corpus_path: Optional[str] = None) -> None:
    """
    Optional helper: ingest corpus if empty and build BM25 index.
    Safe to call at process startup (worker) to avoid first-request latency.
    """
    db = SessionLocal()
    try:
        ingest_corpus(db, corpus_path=corpus_path, skip_if_exists=True)
        get_bm25_index(db)
        # also loads embedding model
        get_embedding_model()
    finally:
        db.close()

