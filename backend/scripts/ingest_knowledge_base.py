import argparse

from app.db import SessionLocal
from app.knowledge_base import ingest_corpus, warmup_knowledge_base


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest curated knowledge corpus into knowledge_chunks.")
    parser.add_argument("--corpus", default=None, help="Path to corpus JSON (defaults to backend/data/knowledge_corpus.json)")
    parser.add_argument("--force", action="store_true", help="Re-ingest even if knowledge_chunks already has rows (not implemented; for now clears cache only).")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        inserted = ingest_corpus(db, corpus_path=args.corpus, skip_if_exists=not args.force)
        print(f"Inserted {inserted} knowledge chunks.")
    finally:
        db.close()

    # Warm caches (BM25 + embedding model)
    warmup_knowledge_base(corpus_path=args.corpus)
    print("Warmup complete.")


if __name__ == "__main__":
    main()

