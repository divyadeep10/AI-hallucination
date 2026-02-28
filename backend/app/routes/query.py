from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.llm import LLMProviderNotConfiguredError, generate_answer
from app.models import Claim, Evidence, Response, Verification, Workflow
from app.models.workflow import WorkflowStatus
from app.queue import get_workflow_queue
from app.agents import (
    run_planner_agent,
    run_generator_agent,
    run_claim_extractor_agent,
    run_retriever_agent,
    run_verification_agent,
    run_critic_agent,
    run_refiner_agent,
)
from app.schemas import (
    ClaimResponse,
    EvidenceResponse,
    QueryRequest,
    QueryResponse,
    StoredResponse,
    VerificationDebugItem,
    WorkflowDebugResponse,
    WorkflowStatusResponse,
)


router = APIRouter(prefix="/api", tags=["query"])


@router.post("/query", response_model=QueryResponse, status_code=status.HTTP_201_CREATED)
async def create_query(payload: QueryRequest, db: Session = Depends(get_db)) -> QueryResponse:
    """
    Create a new workflow for the incoming query and synchronously generate
    a baseline answer using the configured LLM provider.

    This is the Phase 1 baseline path:
    User → Single LLM → Answer (no verification yet).
    """
    query_text = payload.query.strip()
    if not query_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query must not be empty or whitespace-only.",
        )
    workflow = Workflow(user_query=query_text, status=WorkflowStatus.CREATED.value)
    db.add(workflow)
    db.commit()
    db.refresh(workflow)

    try:
        answer = await generate_answer(query_text)
    except LLMProviderNotConfiguredError as exc:
        # Roll back workflow creation if no provider is configured, to avoid
        # leaving unusable records.
        db.delete(workflow)
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Persist the baseline answer as a response row for auditing and comparison.
    baseline_response = Response(
        workflow_id=workflow.id,
        agent_type="BASELINE",
        response_text=answer,
        model_used=_infer_model_used(),
    )
    db.add(baseline_response)

    workflow.status = WorkflowStatus.COMPLETED.value
    workflow.completed_at = datetime.utcnow()
    db.add(workflow)
    db.commit()
    db.refresh(workflow)

    return QueryResponse(
        workflow_id=workflow.id,
        answer=answer,
        status=workflow.status,
    )


@router.post(
    "/workflows",
    response_model=WorkflowStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_workflow_async(
    payload: QueryRequest,
    db: Session = Depends(get_db),
) -> WorkflowStatusResponse:
    """
    Create a new workflow and enqueue the PlannerAgent for asynchronous execution.

    This introduces the Phase 2 orchestration pattern:
    User → Workflow (CREATED) → PlannerAgent (PLANNED) via Redis/RQ queue.
    """
    query_text = payload.query.strip()
    if not query_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query must not be empty or whitespace-only.",
        )
    workflow = Workflow(
        user_query=query_text,
        status=WorkflowStatus.CREATED.value,
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)

    try:
        queue = get_workflow_queue()
        # Enqueue planner → generator → claim extractor → retriever → verification → critic → refiner.
        queue.enqueue(run_planner_agent, workflow.id)
        queue.enqueue(run_generator_agent, workflow.id)
        queue.enqueue(run_claim_extractor_agent, workflow.id)
        queue.enqueue(run_retriever_agent, workflow.id)
        queue.enqueue(run_verification_agent, workflow.id)
        queue.enqueue(run_critic_agent, workflow.id)
        queue.enqueue(run_refiner_agent, workflow.id)
    except Exception as exc:
        # Mark the workflow as FAILED and surface a clear error.
        workflow.status = WorkflowStatus.FAILED.value
        db.add(workflow)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue workflow for processing. Please try again later.",
        ) from exc

    return WorkflowStatusResponse(
        workflow_id=workflow.id,
        status=workflow.status,
        created_at=workflow.created_at,
        completed_at=workflow.completed_at,
        error_message=workflow.error_message,
        stage_timestamps=None,
    )


def _get_stage_timestamps(db: Session, workflow_id: int) -> dict[str, datetime] | None:
    """Compute earliest created_at for claims, evidence, and verifications for this workflow."""
    stage_timestamps: dict[str, datetime] = {}

    # Claims: min(created_at) for claims whose response belongs to this workflow
    claim_min = (
        db.query(func.min(Claim.created_at))
        .join(Response, Claim.response_id == Response.id)
        .filter(Response.workflow_id == workflow_id)
        .scalar()
    )
    if claim_min is not None:
        stage_timestamps["claims_extracted_at"] = claim_min

    # Evidence: min(created_at) for evidence whose claim belongs to this workflow
    evidence_min = (
        db.query(func.min(Evidence.created_at))
        .join(Claim, Evidence.claim_id == Claim.id)
        .join(Response, Claim.response_id == Response.id)
        .filter(Response.workflow_id == workflow_id)
        .scalar()
    )
    if evidence_min is not None:
        stage_timestamps["evidence_retrieved_at"] = evidence_min

    # Verification: min(created_at) for verifications whose claim belongs to this workflow
    verification_min = (
        db.query(func.min(Verification.created_at))
        .join(Claim, Verification.claim_id == Claim.id)
        .join(Response, Claim.response_id == Response.id)
        .filter(Response.workflow_id == workflow_id)
        .scalar()
    )
    if verification_min is not None:
        stage_timestamps["verified_at"] = verification_min

    return stage_timestamps if stage_timestamps else None


@router.get(
    "/workflows/{workflow_id}",
    response_model=WorkflowStatusResponse,
    status_code=status.HTTP_200_OK,
)
def get_workflow_status(workflow_id: int, db: Session = Depends(get_db)) -> WorkflowStatusResponse:
    """
    Retrieve basic status information for a workflow.

    Includes optional stage_timestamps for timeline (claims_extracted_at,
    evidence_retrieved_at, verified_at) when data exists.
    """
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with id {workflow_id} not found.",
        )

    stage_timestamps = _get_stage_timestamps(db, workflow_id)

    return WorkflowStatusResponse(
        workflow_id=workflow.id,
        status=workflow.status,
        created_at=workflow.created_at,
        completed_at=workflow.completed_at,
        error_message=workflow.error_message,
        stage_timestamps=stage_timestamps,
    )


@router.get(
    "/workflows/{workflow_id}/responses",
    response_model=list[StoredResponse],
    status_code=status.HTTP_200_OK,
)
def list_workflow_responses(
    workflow_id: int,
    db: Session = Depends(get_db),
) -> list[StoredResponse]:
    """
    Return all stored responses for a workflow, ordered by timestamp ascending.

    This includes baseline responses (for /api/query) and generator outputs
    (for the asynchronous pipeline).
    """
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with id {workflow_id} not found.",
        )

    responses = (
        db.query(Response)
        .filter(Response.workflow_id == workflow_id)
        .order_by(Response.timestamp.asc())
        .all()
    )
    return [
        StoredResponse(
            id=item.id,
            agent_type=item.agent_type,
            response_text=item.response_text,
            model_used=item.model_used,
            timestamp=item.timestamp,
        )
        for item in responses
    ]


@router.get(
    "/workflows/{workflow_id}/claims",
    response_model=list[ClaimResponse],
    status_code=status.HTTP_200_OK,
)
def list_workflow_claims(
    workflow_id: int,
    db: Session = Depends(get_db),
) -> list[ClaimResponse]:
    """
    Return all extracted claims for a workflow (from generator response(s)).

    Claims are ordered by id. Used for Phase 4 claim-level view; verification
    status will be added in later phases.
    """
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with id {workflow_id} not found.",
        )
    claims = (
        db.query(Claim)
        .join(Response, Claim.response_id == Response.id)
        .filter(Response.workflow_id == workflow_id)
        .order_by(Claim.id.asc())
        .all()
    )
    verification_map = {
        v.claim_id: v
        for v in db.query(Verification).filter(Verification.claim_id.in_([c.id for c in claims]))
    } if claims else {}

    result: list[ClaimResponse] = []
    for c in claims:
        v = verification_map.get(c.id)
        result.append(
            ClaimResponse(
                id=c.id,
                response_id=c.response_id,
                claim_text=c.claim_text,
                entities=c.entities or [],
                extraction_confidence=c.extraction_confidence,
                verification_status=v.status if v else None,
                verification_confidence=v.confidence_score if v else None,
            )
        )
    return result


@router.get(
    "/workflows/{workflow_id}/debug",
    response_model=WorkflowDebugResponse,
    status_code=status.HTTP_200_OK,
)
def get_workflow_debug(
    workflow_id: int,
    db: Session = Depends(get_db),
) -> WorkflowDebugResponse:
    """
    Return full workflow payload for developer/debug view (Phase 7).
    Includes workflow, responses, claims with verification, evidence, and verifications.
    """
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with id {workflow_id} not found.",
        )

    responses = (
        db.query(Response)
        .filter(Response.workflow_id == workflow_id)
        .order_by(Response.timestamp.asc())
        .all()
    )
    claims = (
        db.query(Claim)
        .join(Response, Claim.response_id == Response.id)
        .filter(Response.workflow_id == workflow_id)
        .order_by(Claim.id.asc())
        .all()
    )
    claim_ids = [c.id for c in claims]
    verification_map = (
        {v.claim_id: v for v in db.query(Verification).filter(Verification.claim_id.in_(claim_ids)).all()}
        if claim_ids else {}
    )
    verifications = (
        db.query(Verification).filter(Verification.claim_id.in_(claim_ids)).order_by(Verification.id.asc()).all()
        if claim_ids else []
    )
    evidence_items = (
        db.query(Evidence).filter(Evidence.claim_id.in_(claim_ids)).order_by(Evidence.retrieval_score.desc().nullslast(), Evidence.id.asc()).all()
        if claim_ids else []
    )

    claims_payload = [
        ClaimResponse(
            id=c.id,
            response_id=c.response_id,
            claim_text=c.claim_text,
            entities=c.entities or [],
            extraction_confidence=c.extraction_confidence,
            verification_status=(v := verification_map.get(c.id)) and v.status or None,
            verification_confidence=(v and v.confidence_score),
        )
        for c in claims
    ]
    return WorkflowDebugResponse(
        workflow=WorkflowStatusResponse(
            workflow_id=workflow.id,
            status=workflow.status,
            created_at=workflow.created_at,
            completed_at=workflow.completed_at,
            error_message=workflow.error_message,
            stage_timestamps=_get_stage_timestamps(db, workflow.id),
        ),
        responses=[
            StoredResponse(
                id=r.id,
                agent_type=r.agent_type,
                response_text=r.response_text,
                model_used=r.model_used,
                timestamp=r.timestamp,
            )
            for r in responses
        ],
        claims=claims_payload,
        evidence=[
            EvidenceResponse(
                id=e.id,
                claim_id=e.claim_id,
                source_url=e.source_url,
                snippet=e.snippet,
                retrieval_score=e.retrieval_score,
            )
            for e in evidence_items
        ],
        verifications=[
            VerificationDebugItem(
                id=v.id,
                claim_id=v.claim_id,
                status=v.status,
                confidence_score=v.confidence_score,
                evidence_id=v.evidence_id,
            )
            for v in verifications
        ],
    )


@router.get(
    "/claims/{claim_id}/evidence",
    response_model=list[EvidenceResponse],
    status_code=status.HTTP_200_OK,
)
def list_claim_evidence(
    claim_id: int,
    db: Session = Depends(get_db),
) -> list[EvidenceResponse]:
    """
    Return evidence rows for a single claim, ordered by retrieval_score descending
    (fallback to id when score is null).
    """
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Claim with id {claim_id} not found.",
        )
    query = db.query(Evidence).filter(Evidence.claim_id == claim_id)
    # Order by retrieval_score when present, otherwise by id for stability.
    evidence_items = (
        query.order_by(Evidence.retrieval_score.desc().nullslast(), Evidence.id.asc())
        .all()
    )
    return [
        EvidenceResponse(
            id=e.id,
            claim_id=e.claim_id,
            source_url=e.source_url,
            snippet=e.snippet,
            retrieval_score=e.retrieval_score,
        )
        for e in evidence_items
    ]


def _infer_model_used() -> str:
    """
    Best-effort indication of which provider/model was used for synchronous queries.
    """
    import os

    if os.getenv("OPENAI_API_KEY"):
        return os.getenv("OPENAI_MODEL", "OPENAI")
    if os.getenv("GEMINI_API_KEY"):
        return os.getenv("GEMINI_MODEL", "GEMINI")
    return "UNCONFIGURED"

