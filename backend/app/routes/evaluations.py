"""
Phase 8: Evaluation runs API.
List and retrieve evaluation runs and their samples (created by run_evaluation script).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import EvaluationRun, EvaluationSample
from app.schemas import (
    EvaluationRunDetailResponse,
    EvaluationRunListResponse,
    EvaluationSampleResponse,
)


router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


@router.get(
    "/runs",
    response_model=list[EvaluationRunListResponse],
    status_code=status.HTTP_200_OK,
)
def list_evaluation_runs(
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
) -> list[EvaluationRunListResponse]:
    """
    List evaluation runs, most recent first.
    Used by the frontend Evaluation Results page.
    """
    if limit < 1 or limit > 200:
        limit = 50
    if offset < 0:
        offset = 0
    runs = (
        db.query(EvaluationRun)
        .order_by(EvaluationRun.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        EvaluationRunListResponse(
            id=r.id,
            name=r.name,
            mode=r.mode,
            status=r.status,
            summary_metrics=r.summary_metrics,
            created_at=r.created_at,
            completed_at=r.completed_at,
        )
        for r in runs
    ]


@router.get(
    "/runs/{run_id}",
    response_model=EvaluationRunDetailResponse,
    status_code=status.HTTP_200_OK,
)
def get_evaluation_run(
    run_id: int,
    db: Session = Depends(get_db),
) -> EvaluationRunDetailResponse:
    """
    Get one evaluation run with all its samples.
    """
    run = db.query(EvaluationRun).filter(EvaluationRun.id == run_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation run with id {run_id} not found.",
        )
    samples = (
        db.query(EvaluationSample)
        .filter(EvaluationSample.evaluation_run_id == run_id)
        .order_by(EvaluationSample.id.asc())
        .all()
    )
    return EvaluationRunDetailResponse(
        id=run.id,
        name=run.name,
        mode=run.mode,
        status=run.status,
        summary_metrics=run.summary_metrics,
        created_at=run.created_at,
        completed_at=run.completed_at,
        error_message=run.error_message,
        samples=[
            EvaluationSampleResponse(
                id=s.id,
                question=s.question,
                workflow_id_baseline=s.workflow_id_baseline,
                workflow_id_system=s.workflow_id_system,
                baseline_answer=s.baseline_answer,
                system_answer=s.system_answer,
                baseline_status=s.baseline_status,
                system_status=s.system_status,
                metrics=s.metrics,
                error_message=s.error_message,
                created_at=s.created_at,
            )
            for s in samples
        ],
    )
