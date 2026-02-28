from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.db import Base


class Response(Base):
    __tablename__ = "responses"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(
        Integer,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_type = Column(String(50), nullable=False)
    response_text = Column(Text, nullable=False)
    model_used = Column(String(100), nullable=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)

