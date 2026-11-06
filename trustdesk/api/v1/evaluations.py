from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from trustdesk.core.database import get_db
from trustdesk.core.exceptions import (
    ActiveEvaluationConflictError,
    BrokerUnavailableError,
    EvaluationNotFoundError,
)
from trustdesk.core.logging import get_logger
from trustdesk.core.security import AgentIdentity, verify_demo_token
from trustdesk.eval.runner import ActiveEvaluationAlreadyRunningError
from trustdesk.models.eval import EvalResult, EvalRun
from trustdesk.schemas.eval import (
    EvaluationDetailResponseSchema,
    EvaluationListResponseSchema,
    EvaluationResultItemSchema,
    EvaluationRunRequestSchema,
    EvaluationRunResponseSchema,
    EvaluationSummarySchema,
)
from trustdesk.worker.reconciliation import reconcile_stale_evaluations
from trustdesk.worker.service import EnqueueUnavailableError, enqueue_evaluation_run

logger = get_logger(__name__)

router = APIRouter(prefix="/evaluations", tags=["Evaluations"])


@router.post(
    "/run",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=EvaluationRunResponseSchema,
)
def run_evaluation_endpoint(
    payload: EvaluationRunRequestSchema = EvaluationRunRequestSchema(),
    db: Session = Depends(get_db),
    _agent: AgentIdentity = Depends(verify_demo_token),
) -> EvaluationRunResponseSchema:
    """Trigger an asynchronous evaluation run over a specified JSONL dataset file.

    1. Checks for active runs in PostgreSQL; if an active run exists, triggers
       pre-flight bounded reconciliation to release stale/orphaned slots before rejecting.
    2. Enqueues background task using preassigned job identifier.
    3. Returns HTTP 202 Accepted on success.
    4. Returns HTTP 409 Conflict if another active evaluation genuinely exists.
    5. Returns HTTP 503 Service Unavailable if Redis broker is unreachable.
    """
    # Pre-flight reconciliation check (Section 4.A):
    # If a run appears active in DB, verify if it is stale and recoverable
    has_active = db.execute(
        select(EvalRun.run_id).where(EvalRun.status.in_(["queued", "running"])).limit(1)
    ).scalar_one_or_none()

    if has_active:
        logger.info("Active evaluation detected in database; triggering pre-flight reconciliation check.")
        try:
            reconciled = reconcile_stale_evaluations()
            if reconciled:
                logger.info("Pre-flight reconciliation recovered %d stale evaluation run(s)", len(reconciled))
        except Exception as exc:
            logger.warning("Pre-flight reconciliation attempt failed: %s", exc)

    # Attempt to enqueue evaluation run
    try:
        run_id, job_id = enqueue_evaluation_run(dataset_path=payload.dataset_path)
    except ActiveEvaluationAlreadyRunningError as exc:
        logger.warning("Rejecting evaluation submission due to active run: %s", exc)
        raise ActiveEvaluationConflictError("An evaluation run is currently active.") from exc
    except EnqueueUnavailableError as exc:
        logger.error("Rejecting evaluation submission due to Redis unavailability: %s", exc)
        raise BrokerUnavailableError("Background job broker is unreachable.") from exc

    return EvaluationRunResponseSchema(
        run_id=str(run_id),
        job_id=job_id,
        status="queued",
        message="Evaluation run accepted and enqueued for background processing.",
    )


@router.get("", response_model=EvaluationListResponseSchema)
def list_evaluations_endpoint(
    limit: int = Query(default=20, ge=1, le=100, description="Maximum number of runs to return"),
    offset: int = Query(default=0, ge=0, description="Offset starting position for pagination"),
    db: Session = Depends(get_db),
    _agent: AgentIdentity = Depends(verify_demo_token),
) -> EvaluationListResponseSchema:
    """List historical evaluation runs with newest-first ordering and bounded pagination."""
    total = db.scalar(select(func.count()).select_from(EvalRun)) or 0

    runs = db.execute(
        select(EvalRun)
        .order_by(EvalRun.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()

    items = [
        EvaluationSummarySchema(
            run_id=str(r.run_id),
            job_id=r.job_id,
            status=r.status,
            total_cases=r.total_cases,
            passed_cases=r.passed_cases,
            created_at=r.created_at,
            started_at=r.started_at,
            finished_at=r.finished_at,
            error_details=r.error_details,
        )
        for r in runs
    ]

    return EvaluationListResponseSchema(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{run_id}", response_model=EvaluationDetailResponseSchema)
def get_evaluation_detail_endpoint(
    run_id: str,
    db: Session = Depends(get_db),
    _agent: AgentIdentity = Depends(verify_demo_token),
) -> EvaluationDetailResponseSchema:
    """Retrieve full evaluation report including metrics summary and per-case results."""
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise EvaluationNotFoundError(run_id=run_id)

    eval_run = db.execute(
        select(EvalRun).where(EvalRun.run_id == run_uuid)
    ).scalar_one_or_none()

    if not eval_run:
        raise EvaluationNotFoundError(run_id=run_id)

    # Query per-case results ordered by source_line_number
    results_query = db.execute(
        select(EvalResult)
        .where(EvalResult.run_id == run_uuid)
        .order_by(EvalResult.source_line_number.asc())
    ).scalars().all()

    result_items = [
        EvaluationResultItemSchema(
            id=str(res.id),
            run_id=str(res.run_id),
            source_line_number=res.source_line_number,
            case_id=res.case_id,
            ticket_id=res.ticket_id,
            validation_status=res.validation_status,
            triage_passed=res.triage_passed,
            citation_passed=res.citation_passed,
            safety_passed=res.safety_passed,
            escalation_passed=res.escalation_passed,
            execution_details=res.execution_details,
            created_at=res.created_at,
        )
        for res in results_query
    ]

    return EvaluationDetailResponseSchema(
        run_id=str(eval_run.run_id),
        job_id=eval_run.job_id,
        status=eval_run.status,
        total_cases=eval_run.total_cases,
        passed_cases=eval_run.passed_cases,
        metrics_summary=eval_run.metrics_summary,
        error_details=eval_run.error_details,
        created_at=eval_run.created_at,
        started_at=eval_run.started_at,
        finished_at=eval_run.finished_at,
        results=result_items,
    )

