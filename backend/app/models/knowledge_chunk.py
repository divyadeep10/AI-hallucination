from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.db import Base


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=False)
    source = Column(String(512), nullable=True, index=True)
    # all-mpnet-base-v2 outputs 768-dim embeddings; stored as JSONB (no pgvector required)
    embedding = Column(JSONB, nullable=False)

