from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from trustdesk.core.database import get_db_session
from trustdesk.core.logging import get_logger
from trustdesk.eval.runner import EvaluationRunner, sanitize_text
from trustdesk.models.eval import EvalRun

logger = get_logger(__name__)


def run_evaluation_task(
    run_id: str,
    dataset_path: str = "./data/eval_cases.jsonl",
) -> dict[str, Any]:
    """RQ background task for asynchronous evaluation suite execution.

    1. Resolves existing queued EvalRun record from PostgreSQL.
    2. Delegates execution to the deterministic EvaluationRunner.
    3. Guarantees persistence of final run status and metrics.
    4. Distinguishes case-level validation failures from fatal run crashes.
    5. In the event of an unhandled crash, marks the database run as 'failed'
       and releases the active-run constraint slot.
    6. Autonomous execution invariant: NEVER executes operational refund actions.
    """
    run_uuid = uuid.UUID(run_id)
    path = Path(dataset_path).resolve()

    logger.info(
        "Starting background evaluation task for run_id=%s with dataset=%s",
        run_uuid,
        path,
    )

    runner = EvaluationRunner()

    try:
        eval_run = asyncio.run(runner.run(dataset_path=path, run_id=run_uuid, enforce_containment=True))
    except Exception as exc:
        logger.error(
            "Evaluation task failed with unhandled exception for run_id=%s: %s",
            run_uuid,
            exc,
            exc_info=True,
        )
        # Ensure database record is updated to failed to release single-active-run slot
        try:
            with get_db_session() as session:
                run_rec = session.execute(
                    select(EvalRun).where(EvalRun.run_id == run_uuid)
                ).scalar_one_or_none()
                if run_rec and run_rec.status in ("queued", "running"):
                    run_rec.status = "failed"
                    run_rec.finished_at = datetime.now(timezone.utc)
                    run_rec.error_details = {
                        "error_code": "WORKER_EXECUTION_FAILURE",
                        "error_type": type(exc).__name__,
                        "message": sanitize_text(str(exc)),
                    }
                    session.commit()
                    logger.info("Successfully marked run_id=%s as failed in database", run_uuid)
        except Exception as db_exc:
            logger.critical(
                "Failed to update EvalRun status for run_id=%s during failure handler: %s",
                run_uuid,
                db_exc,
            )
        raise

    logger.info(
        "Background evaluation task finished for run_id=%s with status=%s (passed=%d/%d)",
        eval_run.run_id,
        eval_run.status,
        eval_run.passed_cases,
        eval_run.total_cases,
    )

    return {
        "run_id": str(eval_run.run_id),
        "job_id": eval_run.job_id,
        "status": eval_run.status,
        "total_cases": eval_run.total_cases,
        "passed_cases": eval_run.passed_cases,
    }

