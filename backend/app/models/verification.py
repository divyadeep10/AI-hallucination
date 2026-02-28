from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String

from app.db import Base


class Verification(Base):
    """
    Stores verification status per claim (PDF §16, §22).

    Each row represents the outcome of verifying a single claim, optionally
    linked to the evidence row used for the decision.
    """

    __tablename__ = "verification"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(
        Integer,
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String(50), nullable=False)
    confidence_score = Column(Float, nullable=True)
    evidence_id = Column(
        Integer,
        ForeignKey("evidence.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

