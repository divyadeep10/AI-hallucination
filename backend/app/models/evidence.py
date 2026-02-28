from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.db import Base


class Evidence(Base):
    """
    Stores retrieval evidence for a claim (PDF §16).

    Each row corresponds to a snippet retrieved for a particular claim along
    with its source and a retrieval_score used for ranking.
    is_external=True when the snippet comes from web search (Playwright) rather than internal KB.
    """

    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(
        Integer,
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_url = Column(String(500), nullable=True)
    snippet = Column(Text, nullable=False)
    retrieval_score = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    is_external = Column(Boolean, nullable=False, default=False)

