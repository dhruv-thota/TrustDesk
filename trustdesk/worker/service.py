from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from rq import Queue
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from trustdesk.core.config import settings
from trustdesk.core.database import get_db_session
from trustdesk.core.logging import get_logger
from trustdesk.core.redis import get_redis_client
from trustdesk.eval.runner import ActiveEvaluationAlreadyRunningError, sanitize_text
from trustdesk.models.eval import EvalRun
from trustdesk.worker.tasks import run_evaluation_task

logger = get_logger(__name__)


class EnqueueUnavailableError(Exception):
    """Raised when enqueuing a background task to the Redis broker fails."""
    pass


def enqueue_evaluation_run(
    dataset_path: str = "./data/eval_cases.jsonl",
    run_id: uuid.UUID | None = None,
    job_id: str | None = None,
) -> tuple[uuid.UUID, str]:
    """Atomic evaluation enqueue protocol with preassigned job identifiers.

    Enforces the following ordering:
    1. Generate stable RQ job ID and PostgreSQL run ID.
    2. Create and commit EvalRun(status="queued") in PostgreSQL.
       (Rejects duplicate/concurrent active runs via idx_single_active_eval_run).
    3. Enqueue the task in Redis via RQ using the preassigned job ID.
    4. If Redis enqueue fails:
       - Update EvalRun record to status="failed".
       - Cleanly release the idx_single_active_eval_run constraint slot.
       - Raise typed EnqueueUnavailableError.
    5. Return (run_id, job_id) only after successful enqueue.
    """
    target_run_id = run_id or uuid.uuid4()
    target_job_id = job_id or f"eval-job-{target_run_id.hex[:12]}"
    path_str = str(Path(dataset_path).resolve())
    now_utc = datetime.now(timezone.utc)

    # Step 1: Create and commit queued record in PostgreSQL
    with get_db_session() as session:
        eval_run = EvalRun(
            run_id=target_run_id,
            job_id=target_job_id,
            status="queued",
            total_cases=0,
            passed_cases=0,
            metrics_summary={},
            error_details=None,
            created_at=now_utc,
            started_at=None,
            finished_at=None,
        )
        session.add(eval_run)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            msg = (
                f"Cannot enqueue evaluation run: another active run is currently "
                f"queued or running ({exc})"
            )
            logger.warning(msg)
            raise ActiveEvaluationAlreadyRunningError(msg) from exc

    # Step 2: Enqueue in Redis queue using preassigned job ID
    try:
        redis_client = get_redis_client()
        queue = Queue(settings.rq_queue_name, connection=redis_client)
        queue.enqueue(
            run_evaluation_task,
            str(target_run_id),
            path_str,
            job_id=target_job_id,
            job_timeout="300s",
            result_ttl=86400,
        )
        logger.info(
            "Successfully enqueued evaluation run: run_id=%s, job_id=%s",
            target_run_id,
            target_job_id,
        )
    except Exception as exc:
        logger.error(
            "Redis enqueue failed for run_id=%s (job_id=%s): %s. Releasing active slot.",
            target_run_id,
            target_job_id,
            exc,
        )
        # Update run to failed and release the single-active-run slot
        try:
            with get_db_session() as session:
                run_rec = session.execute(
                    select(EvalRun).where(EvalRun.run_id == target_run_id)
                ).scalar_one_or_none()
                if run_rec and run_rec.status == "queued":
                    run_rec.status = "failed"
                    run_rec.finished_at = datetime.now(timezone.utc)
                    run_rec.error_details = {
                        "error_code": "REDIS_UNAVAILABLE",
                        "error_type": type(exc).__name__,
                        "message": sanitize_text(str(exc)),
                    }
                    session.commit()
                    logger.info("Released active-run slot for failed enqueue run_id=%s", target_run_id)
        except Exception as db_exc:
            logger.critical(
                "Failed to mark EvalRun as failed after Redis enqueue error for run_id=%s: %s",
                target_run_id,
                db_exc,
            )
        raise EnqueueUnavailableError(
            f"Background job broker is unreachable: {type(exc).__name__}"
        ) from exc

    return target_run_id, target_job_id

