from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.db import Base


class WorkflowStatus(str, Enum):
    CREATED = "CREATED"
    PLANNED = "PLANNED"
    GENERATED = "GENERATED"
    CLAIMS_EXTRACTED = "CLAIMS_EXTRACTED"
    EVIDENCE_RETRIEVED = "EVIDENCE_RETRIEVED"
    VERIFIED = "VERIFIED"
    CRITIC_REVIEWED = "CRITIC_REVIEWED"
    REFINED = "REFINED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, index=True)
    user_query = Column(Text, nullable=False)
    status = Column(
        String(50),
        nullable=False,
        default=WorkflowStatus.CREATED.value,
        index=True,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

