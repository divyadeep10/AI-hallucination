from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, Text
from sqlalchemy.types import JSON

from app.db import Base


class Claim(Base):
    """
    Stores a single factual claim extracted from a generator response.

    Aligns with PDF §16: claim_id, response_id, claim_text, entities,
    extraction_confidence. Used for claim-level verification in later phases.
    """

    __tablename__ = "claims"

    id = Column(Integer, primary_key=True, index=True)
    response_id = Column(
        Integer,
        ForeignKey("responses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim_text = Column(Text, nullable=False)
    # JSON array of entity strings, e.g. ["TCP", "congestion", "packet loss"]
    entities = Column(JSON, nullable=False, default=list)
    extraction_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
