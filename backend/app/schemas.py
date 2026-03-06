from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=15000,
        description="User's natural language question.",
    )


class QueryResponse(BaseModel):
    workflow_id: int
    answer: str
    status: str


class WorkflowStatusResponse(BaseModel):
    workflow_id: int
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    # Stage timestamps for timeline (min created_at per stage)
    stage_timestamps: Optional[dict[str, datetime]] = None


class StoredResponse(BaseModel):
    id: int
    agent_type: str
    response_text: str
    model_used: Optional[str] = None
    timestamp: datetime


class ClaimResponse(BaseModel):
    id: int
    response_id: int
    claim_text: str
    entities: list[str] = []
    extraction_confidence: Optional[float] = None

    verification_status: Optional[str] = None
    verification_confidence: Optional[float] = None


class EvidenceResponse(BaseModel):
    id: int
    claim_id: int
    source_url: Optional[str] = None
    snippet: str
    retrieval_score: Optional[float] = None
    is_external: bool = False
    source: Optional[str] = None  # 'internal' | 'wikipedia' | 'wikidata' | 'external'


class VerificationDebugItem(BaseModel):
    """Single verification record for debug/developer view."""

    id: int
    claim_id: int
    status: str
    confidence_score: Optional[float] = None
    evidence_id: Optional[int] = None


class WorkflowDebugResponse(BaseModel):
    """
    Full workflow payload for Phase 7 developer/debug view.
    Includes workflow, responses, claims (with verification), evidence, and verifications.
    """

    workflow: WorkflowStatusResponse
    responses: list[StoredResponse]
    claims: list[ClaimResponse]
    evidence: list[EvidenceResponse]
    verifications: list[VerificationDebugItem]


# --- Phase 8: Evaluation ---

class EvaluationSampleResponse(BaseModel):
    """One sample (question) in an evaluation run."""

    id: int
    question: str
    workflow_id_baseline: Optional[int] = None
    workflow_id_system: Optional[int] = None
    baseline_answer: Optional[str] = None
    system_answer: Optional[str] = None
    baseline_status: Optional[str] = None
    system_status: Optional[str] = None
    metrics: Optional[dict] = None
    error_message: Optional[str] = None
    created_at: datetime


class EvaluationRunListResponse(BaseModel):
    """Evaluation run summary for list view."""

    id: int
    name: Optional[str] = None
    mode: str
    status: str
    summary_metrics: Optional[dict] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class EvaluationRunDetailResponse(BaseModel):
    """Evaluation run with samples for detail view."""

    id: int
    name: Optional[str] = None
    mode: str
    status: str
    summary_metrics: Optional[dict] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    samples: list[EvaluationSampleResponse]

