from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import redis
from rq import Queue, Worker
from rq.registry import (
    DeferredJobRegistry,
    FailedJobRegistry,
    FinishedJobRegistry,
    StartedJobRegistry,
)
from sqlalchemy import select

from trustdesk.core.config import settings
from trustdesk.core.database import get_db_session
from trustdesk.core.logging import get_logger
from trustdesk.core.redis import check_redis_connection, get_redis_client
from trustdesk.models.eval import EvalRun

logger = get_logger(__name__)


def reconcile_stale_evaluations(
    stale_queued_seconds: int | None = None,
    heartbeat_timeout_seconds: int | None = None,
    redis_client: redis.Redis | None = None,
) -> list[dict[str, Any]]:
    """Bounded, safe failure reconciliation for stale queued and running evaluations.

    Rules:
    1. A temporary Redis outage must NEVER mark evaluations as failed; if Redis is
       unreachable, the sweep safely aborts without mutating database state.
    2. Stale queued records (> stale_queued_seconds, default 60s) whose job_id is
       absent from all Redis queues and registries are transitioned to 'failed'
       with error_code='ENQUEUE_ORPHANED' (P7-EC-003).
    3. Stale running records (> heartbeat_timeout_seconds, default 120s) whose worker
       is dead or whose job is in FailedJobRegistry or missing from StartedJobRegistry
       are transitioned to 'failed' with error_code='WORKER_INTERRUPTED' (P7-EC-004).
    4. Operation is strictly idempotent.
    """
    queued_threshold = (
        stale_queued_seconds
        if stale_queued_seconds is not None
        else settings.worker_stale_threshold_seconds
    )
    running_threshold = (
        heartbeat_timeout_seconds
        if heartbeat_timeout_seconds is not None
        else settings.worker_heartbeat_timeout_seconds
    )

    client = redis_client or get_redis_client()

    # Rule 1: Safe abort on Redis outage without mutating database state
    try:
        check_redis_connection(client)
    except Exception as exc:
        logger.warning(
            "Redis broker is unreachable during reconciliation sweep (%s); aborting sweep safely.",
            exc,
        )
        return []

    reconciled: list[dict[str, Any]] = []
    now_utc = datetime.now(timezone.utc)

    try:
        queue = Queue(settings.rq_queue_name, connection=client)
        started_registry = StartedJobRegistry(queue=queue)
        deferred_registry = DeferredJobRegistry(queue=queue)
        failed_registry = FailedJobRegistry(queue=queue)
        queued_job_ids = set(queue.job_ids)
        started_job_ids = set(started_registry.get_job_ids())
        deferred_job_ids = set(deferred_registry.get_job_ids())
        failed_job_ids = set(failed_registry.get_job_ids())

        # Inspect active workers
        active_workers = Worker.all(connection=client)
        active_worker_job_ids = {
            w.get_current_job_id() for w in active_workers if w.get_current_job_id()
        }
    except Exception as exc:
        logger.warning(
            "Failed to inspect RQ registries during reconciliation sweep: %s; aborting.",
            exc,
        )
        return []

    with get_db_session() as session:
        active_runs = session.execute(
            select(EvalRun).where(EvalRun.status.in_(["queued", "running"]))
        ).scalars().all()

        for run in active_runs:
            if run.status == "queued":
                age_seconds = (now_utc - run.created_at).total_seconds()
                if age_seconds > queued_threshold:
                    # Check if present in any queued/active Redis structure
                    in_redis = (
                        run.job_id in queued_job_ids
                        or run.job_id in started_job_ids
                        or run.job_id in deferred_job_ids
                    )
                    if not in_redis:
                        logger.warning(
                            "Reconciling orphaned queued evaluation run_id=%s (job_id=%s, age=%.1fs)",
                            run.run_id,
                            run.job_id,
                            age_seconds,
                        )
                        run.status = "failed"
                        run.finished_at = now_utc
                        run.error_details = {
                            "error_code": "ENQUEUE_ORPHANED",
                            "message": "API process crashed before Redis enqueue completed",
                            "age_seconds": round(age_seconds, 1),
                        }
                        reconciled.append({
                            "run_id": str(run.run_id),
                            "job_id": run.job_id,
                            "previous_status": "queued",
                            "reconciled_status": "failed",
                            "reason": "ENQUEUE_ORPHANED",
                        })

            elif run.status == "running":
                reference_time = run.started_at or run.created_at
                age_seconds = (now_utc - reference_time).total_seconds()

                if age_seconds > running_threshold:
                    job_is_failed = run.job_id in failed_job_ids
                    job_is_active = (
                        run.job_id in started_job_ids
                        or run.job_id in active_worker_job_ids
                    )

                    if job_is_failed or not job_is_active:
                        logger.warning(
                            "Reconciling interrupted running evaluation run_id=%s (job_id=%s, age=%.1fs)",
                            run.run_id,
                            run.job_id,
                            age_seconds,
                        )
                        run.status = "failed"
                        run.finished_at = now_utc
                        run.error_details = {
                            "error_code": "WORKER_INTERRUPTED",
                            "message": "Worker process terminated unexpectedly or job failed in queue",
                            "age_seconds": round(age_seconds, 1),
                        }
                        reconciled.append({
                            "run_id": str(run.run_id),
                            "job_id": run.job_id,
                            "previous_status": "running",
                            "reconciled_status": "failed",
                            "reason": "WORKER_INTERRUPTED",
                        })

        if reconciled:
            session.commit()
            logger.info("Reconciliation sweep completed: reconciled %d run(s)", len(reconciled))

    return reconciled

