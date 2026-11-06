from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from trustdesk.core.database import get_db
from trustdesk.core.exceptions import JobNotFoundError
from trustdesk.core.security import AgentIdentity, verify_demo_token
from trustdesk.models.eval import EvalRun
from trustdesk.schemas.eval import JobStatusResponseSchema

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("/{job_id}", response_model=JobStatusResponseSchema)
def get_job_status_endpoint(
    job_id: str,
    db: Session = Depends(get_db),
    _agent: AgentIdentity = Depends(verify_demo_token),
) -> JobStatusResponseSchema:
    """Poll the status of an asynchronous background job.

    1. Resolves job status directly from authoritative PostgreSQL persistence.
    2. Does not require Redis connectivity merely to read persisted job status.
    3. Returns 404 Not Found for unknown job identifiers.
    4. Does not infer success from ephemeral RQ job registries.
    """
    eval_run = db.execute(
        select(EvalRun).where(EvalRun.job_id == job_id)
    ).scalar_one_or_none()

    if not eval_run:
        raise JobNotFoundError(job_id=job_id)

    return JobStatusResponseSchema(
        job_id=eval_run.job_id,
        run_id=str(eval_run.run_id),
        status=eval_run.status,
        total_cases=eval_run.total_cases,
        passed_cases=eval_run.passed_cases,
        created_at=eval_run.created_at,
        started_at=eval_run.started_at,
        finished_at=eval_run.finished_at,
        error_details=eval_run.error_details,
    )

