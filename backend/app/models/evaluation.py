"""
Phase 8: Evaluation run and sample models for reproducibility.
Stores evaluation runs (baseline and/or full pipeline) and per-question metrics.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.types import JSON

from app.db import Base


class EvaluationRun(Base):
    """
    One evaluation run over a dataset (baseline only, full pipeline only, or both).
    summary_metrics holds aggregated metrics for the run.
    """

    __tablename__ = "evaluation_runs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=True)
    mode = Column(String(50), nullable=False)  # baseline | full_pipeline | both
    dataset_path = Column(String(512), nullable=True)
    status = Column(String(50), nullable=False, default="running", index=True)  # running | completed | failed
    summary_metrics = Column(JSON, nullable=True)  # e.g. num_questions, claim_verification_accuracy, etc.
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)  # run-level failure reason


class EvaluationSample(Base):
    """
    One question evaluated in a run. Stores workflow ids, answers, and per-sample metrics.
    """

    __tablename__ = "evaluation_samples"

    id = Column(Integer, primary_key=True, index=True)
    evaluation_run_id = Column(
        Integer,
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question = Column(Text, nullable=False)
    workflow_id_baseline = Column(Integer, nullable=True)
    workflow_id_system = Column(Integer, nullable=True)
    baseline_answer = Column(Text, nullable=True)
    system_answer = Column(Text, nullable=True)
    baseline_status = Column(String(50), nullable=True)
    system_status = Column(String(50), nullable=True)
    metrics = Column(JSON, nullable=True)  # num_claims, num_supported, claim_verification_accuracy, etc.
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
