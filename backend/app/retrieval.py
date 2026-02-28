from typing import Any

from app.db import SessionLocal
from app.knowledge_base import (
    embedding_search,
    get_bm25_index,
    ingest_corpus,
 )

"""
Retrieval module (Phase 5).

This file defines the retrieval API used by the RetrieverAgent. In the full
system, this would implement hybrid retrieval (BM25 + embeddings) over an
external knowledge base as described in the design document (PDF §21).

This module now implements a real hybrid retriever over a curated knowledge base:
- Embedding-based semantic search (pgvector cosine similarity)
- BM25 keyword search (rank_bm25) over knowledge_chunks text
- Score fusion: final = 0.6 * embedding_sim + 0.4 * bm25_norm

It intentionally keeps the public API used by RetrieverAgent unchanged.
"""


def retrieve_evidence_for_claim(claim_text: str) -> list[dict[str, Any]]:
    """
    Retrieve evidence snippets for a given claim.

    Returns a list of dicts with keys:
    - source_url: str | None
    - snippet: str
    - retrieval_score: float | None

    Hybrid retrieval implementation:
    - Embedding search in PostgreSQL over knowledge_chunks.embedding (pgvector)
    - BM25 search in-memory over knowledge_chunks.text
    - Fusion and return top evidence snippets as dicts compatible with Evidence model
    """
    text = (claim_text or "").strip()
    if not text:
        return []

    db = SessionLocal()
    try:
        # Ensure we have at least a small corpus ingested.
        ingest_corpus(db, skip_if_exists=True)

        # 1) Embedding search
        emb_hits = embedding_search(db, text, top_k=12)
        emb_scores: dict[int, float] = {chunk.id: float(sim) for chunk, sim in emb_hits}
        chunk_by_id = {chunk.id: chunk for chunk, _ in emb_hits}

        # 2) BM25 search (cached index)
        bm25 = get_bm25_index(db)
        bm25_scores = bm25.query(text, top_k=30)  # id -> norm score 0..1

        # 3) Fuse candidates
        candidate_ids = set(emb_scores.keys()) | set(bm25_scores.keys())
        if not candidate_ids:
            return []

        # Load any missing chunks needed for fusion output
        missing_ids = [i for i in candidate_ids if i not in chunk_by_id]
        if missing_ids:
            from app.models.knowledge_chunk import KnowledgeChunk

            rows = db.query(KnowledgeChunk).filter(KnowledgeChunk.id.in_(missing_ids)).all()
            for r in rows:
                chunk_by_id[r.id] = r

        fused: list[tuple[int, float]] = []
        for cid in candidate_ids:
            es = emb_scores.get(cid, 0.0)
            bs = bm25_scores.get(cid, 0.0)
            final = 0.6 * float(es) + 0.4 * float(bs)
            fused.append((cid, float(final)))

        fused.sort(key=lambda x: x[1], reverse=True)
        top = fused[:5]

        results: list[dict[str, Any]] = []
        for cid, score in top:
            chunk = chunk_by_id.get(cid)
            if not chunk:
                continue
            snippet = (chunk.text or "").strip()
            if not snippet:
                continue
            results.append(
                {
                    "source_url": chunk.source,
                    "snippet": snippet,
                    "retrieval_score": score,
                }
            )
        return results
    finally:
        db.close()

