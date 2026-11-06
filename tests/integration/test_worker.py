from __future__ import annotations

import asyncio
import os
import signal
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import redis
from rq import Queue, SimpleWorker, Worker
from rq.registry import FailedJobRegistry, StartedJobRegistry
from sqlalchemy import func, select, text

from trustdesk.core.config import settings
from trustdesk.core.database import get_db_session
from trustdesk.core.redis import get_redis_client
from trustdesk.eval.runner import (
    ActiveEvaluationAlreadyRunningError,
    EvaluationRunner,
    RunAlreadyCompletedError,
    RunAlreadyFailedError,
    sanitize_diagnostics,
    sanitize_text,
    sanitize_value,
)
from trustdesk.models.action import ProposedAction
from trustdesk.models.eval import EvalResult, EvalRun
from trustdesk.models.knowledge import KBSection
from trustdesk.services.ingestion import ingest_kb_documents
from trustdesk.services.knowledge_service import derive_and_index_sections
from trustdesk.worker.reconciliation import reconcile_stale_evaluations
from trustdesk.worker.service import EnqueueUnavailableError, enqueue_evaluation_run
from trustdesk.worker.tasks import run_evaluation_task

DATASET_PATH = Path("data/eval_cases.jsonl")


@pytest.fixture(autouse=True)
def clean_environment():
    """Ensure database tables, KB sections, and Redis queues are clean before each test."""
    # 1. Clean Database
    with get_db_session() as session:
        session.execute(
            text("TRUNCATE TABLE action_idempotency, proposed_actions, eval_results, eval_runs CASCADE;")
        )
        kb_count = session.scalar(select(func.count()).select_from(KBSection))
        if kb_count < 9:
            session.execute(text("TRUNCATE TABLE kb_sections, kb_documents CASCADE;"))
            ingest_kb_documents(session, Path("./data/kb_documents.json"))
            derive_and_index_sections(session)
        session.commit()

    # 2. Clean Redis
    try:
        client = get_redis_client()
        client.flushdb()
    except Exception:
        pass

    yield

    # Teardown
    with get_db_session() as session:
        session.execute(
            text("TRUNCATE TABLE action_idempotency, proposed_actions, eval_results, eval_runs CASCADE;")
        )
        session.commit()
    try:
        client = get_redis_client()
        client.flushdb()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Test Scenarios
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_existing_queued_run_promotion() -> None:
    """1. Verifies that a worker claims an existing queued EvalRun and transitions it to running."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    now_utc = datetime.now(timezone.utc)

    with get_db_session() as session:
        run = EvalRun(
            run_id=run_id,
            job_id=job_id,
            status="queued",
            created_at=now_utc,
        )
        session.add(run)
        session.commit()

    runner = EvaluationRunner()
    eval_run = await runner.run(dataset_path=DATASET_PATH, run_id=run_id)

    assert eval_run.run_id == run_id
    assert eval_run.status == "completed"
    assert eval_run.started_at is not None
    assert eval_run.total_cases == 18

    with get_db_session() as session:
        persisted = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        assert persisted.status == "completed"
        assert persisted.started_at is not None


@pytest.mark.asyncio
async def test_completed_run_re_execution_prevention() -> None:
    """2. Verifies that attempting to run an already completed run raises RunAlreadyCompletedError."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    now_utc = datetime.now(timezone.utc)

    with get_db_session() as session:
        run = EvalRun(
            run_id=run_id,
            job_id=job_id,
            status="completed",
            created_at=now_utc,
            started_at=now_utc,
            finished_at=now_utc,
            total_cases=18,
            passed_cases=9,
        )
        session.add(run)
        session.commit()

    runner = EvaluationRunner()
    with pytest.raises(RunAlreadyCompletedError) as exc_info:
        await runner.run(dataset_path=DATASET_PATH, run_id=run_id)

    assert "already completed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_failed_run_retry_prevention() -> None:
    """3. Verifies that attempting to re-execute an already failed run raises RunAlreadyFailedError."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    now_utc = datetime.now(timezone.utc)

    with get_db_session() as session:
        run = EvalRun(
            run_id=run_id,
            job_id=job_id,
            status="failed",
            created_at=now_utc,
            started_at=now_utc,
            finished_at=now_utc,
            error_details={"error_code": "DATASET_VALIDATION_ERROR"},
        )
        session.add(run)
        session.commit()

    runner = EvaluationRunner()
    with pytest.raises(RunAlreadyFailedError) as exc_info:
        await runner.run(dataset_path=DATASET_PATH, run_id=run_id)

    assert "already failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_concurrent_worker_claims() -> None:
    """4. Verifies that if a run is already 'running', a concurrent claim raises ActiveEvaluationAlreadyRunningError."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    now_utc = datetime.now(timezone.utc)

    with get_db_session() as session:
        run = EvalRun(
            run_id=run_id,
            job_id=job_id,
            status="running",
            created_at=now_utc,
            started_at=now_utc,
        )
        session.add(run)
        session.commit()

    runner = EvaluationRunner()
    with pytest.raises(ActiveEvaluationAlreadyRunningError) as exc_info:
        await runner.run(dataset_path=DATASET_PATH, run_id=run_id)

    assert "already running" in str(exc_info.value)


def test_recursive_sanitization() -> None:
    """5. Verifies recursive diagnostic sanitization on nested dicts, lists, sensitive keys, and depth bounding."""
    raw_telemetry = {
        "api_key": "AIzaSyD-1234567890abcdefghijklmnopqrst",
        "secret_token": "SECRET-9988776655",
        "authorization_header": "Bearer secret_token_xyz",
        "nested_dict": {
            "user_email": "customer@example.com",
            "card_number": "4111 2222 3333 4444",
            "safe_field": 42,
        },
        "nested_list_of_dicts": [
            {"token": "SECRET-111", "msg": "Email me at support@trustdesk.com"},
            {"card": "5500 0000 0000 0004", "clean": "ok"},
        ],
        "list_of_lists": [["safe", "user@test.org"]],
    }

    sanitized = sanitize_diagnostics(raw_telemetry)

    # Key-based redactions
    assert sanitized["api_key"] == "[REDACTED_SECRET]"
    assert sanitized["secret_token"] == "[REDACTED_SECRET]"
    assert sanitized["authorization_header"] == "[REDACTED_SECRET]"

    # Nested dict string pattern redactions
    assert sanitized["nested_dict"]["user_email"] == "[REDACTED_EMAIL]"
    assert sanitized["nested_dict"]["card_number"] == "[REDACTED_CARD]"
    assert sanitized["nested_dict"]["safe_field"] == 42

    # Nested list of dicts redactions
    assert sanitized["nested_list_of_dicts"][0]["token"] == "[REDACTED_SECRET]"
    assert sanitized["nested_list_of_dicts"][0]["msg"] == "Email me at [REDACTED_EMAIL]"
    assert sanitized["nested_list_of_dicts"][1]["card"] == "[REDACTED_CARD]"
    assert sanitized["nested_list_of_dicts"][1]["clean"] == "ok"

    # List of lists
    assert sanitized["list_of_lists"][0][0] == "safe"
    assert sanitized["list_of_lists"][0][1] == "[REDACTED_EMAIL]"

    # Depth bounding
    deep: dict[str, Any] = {"a": {"b": {"c": {"d": {"e": {"f": {"g": "too deep"}}}}}}}
    sanitized_deep = sanitize_diagnostics(deep)
    assert sanitized_deep["a"]["b"]["c"]["d"]["e"]["f"] == "[TRUNCATED_DEPTH]"


def test_successful_rq_task_execution() -> None:
    """6. Verifies that RQ worker task executes the evaluation suite and records completed status."""
    run_id, job_id = enqueue_evaluation_run(dataset_path=str(DATASET_PATH))

    # Verify run is queued in DB
    with get_db_session() as session:
        initial = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        assert initial.status == "queued"

    # Execute task via RQ worker burst mode
    client = get_redis_client()
    queue = Queue(settings.rq_queue_name, connection=client)
    worker = SimpleWorker([queue], connection=client)
    worker.work(burst=True)

    # Verify run completed in DB
    with get_db_session() as session:
        completed = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        assert completed.status == "completed"
        assert completed.total_cases == 18
        assert completed.passed_cases == 9
        assert completed.metrics_summary["input_accounting"]["is_valid"] is True


def test_enqueue_failure_cleanup() -> None:
    """7. Verifies P7-EC-001: When Redis enqueue fails, DB record is marked failed and active slot is released."""
    run_id = uuid.uuid4()

    with patch("trustdesk.worker.service.Queue.enqueue", side_effect=redis.exceptions.ConnectionError("Redis down")):
        with pytest.raises(EnqueueUnavailableError) as exc_info:
            enqueue_evaluation_run(dataset_path=str(DATASET_PATH), run_id=run_id)

        assert "Background job broker is unreachable" in str(exc_info.value)

    # Check that database status is 'failed' and error_code is REDIS_UNAVAILABLE
    with get_db_session() as session:
        run = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        assert run.status == "failed"
        assert run.error_details["error_code"] == "REDIS_UNAVAILABLE"

    # Slot is released: another run can be enqueued immediately
    next_run_id, next_job_id = enqueue_evaluation_run(dataset_path=str(DATASET_PATH))
    assert next_run_id != run_id


def test_redis_unavailable_during_enqueue() -> None:
    """8. Verifies typed EnqueueUnavailableError when Redis client cannot connect."""
    with patch("trustdesk.worker.service.get_redis_client", side_effect=redis.exceptions.ConnectionError("Connection refused")):
        with pytest.raises(EnqueueUnavailableError):
            enqueue_evaluation_run(dataset_path=str(DATASET_PATH))


def test_worker_exception_handling() -> None:
    """9. Verifies that unhandled exceptions inside worker task mark EvalRun as failed in DB."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    now_utc = datetime.now(timezone.utc)

    with get_db_session() as session:
        run = EvalRun(run_id=run_id, job_id=job_id, status="queued", created_at=now_utc)
        session.add(run)
        session.commit()

    with patch.object(EvaluationRunner, "run", side_effect=RuntimeError("Simulated unhandled worker crash")):
        with pytest.raises(RuntimeError):
            run_evaluation_task(str(run_id), dataset_path=str(DATASET_PATH))

    # Verify that run in DB transitioned to 'failed'
    with get_db_session() as session:
        rec = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        assert rec.status == "failed"
        assert rec.error_details["error_code"] == "WORKER_EXECUTION_FAILURE"
        assert "Simulated unhandled worker crash" in rec.error_details["message"]


def test_worker_interruption_reconciliation() -> None:
    """10. Verifies P7-EC-004: Stale running evaluation whose worker died is reconciled to failed."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    old_time = datetime.now(timezone.utc) - timedelta(seconds=150)

    with get_db_session() as session:
        run = EvalRun(
            run_id=run_id,
            job_id=job_id,
            status="running",
            created_at=old_time,
            started_at=old_time,
        )
        session.add(run)
        session.commit()

    # Trigger reconciliation sweep
    reconciled = reconcile_stale_evaluations(heartbeat_timeout_seconds=120)

    assert len(reconciled) == 1
    assert reconciled[0]["run_id"] == str(run_id)
    assert reconciled[0]["reason"] == "WORKER_INTERRUPTED"

    with get_db_session() as session:
        rec = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        assert rec.status == "failed"
        assert rec.error_details["error_code"] == "WORKER_INTERRUPTED"


def test_stale_queued_reconciliation() -> None:
    """11. Verifies P7-EC-003: Stale queued evaluation absent from Redis is reconciled to failed."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    old_time = datetime.now(timezone.utc) - timedelta(seconds=90)

    with get_db_session() as session:
        run = EvalRun(
            run_id=run_id,
            job_id=job_id,
            status="queued",
            created_at=old_time,
        )
        session.add(run)
        session.commit()

    # Trigger reconciliation sweep (threshold 60s)
    reconciled = reconcile_stale_evaluations(stale_queued_seconds=60)

    assert len(reconciled) == 1
    assert reconciled[0]["run_id"] == str(run_id)
    assert reconciled[0]["reason"] == "ENQUEUE_ORPHANED"

    with get_db_session() as session:
        rec = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        assert rec.status == "failed"
        assert rec.error_details["error_code"] == "ENQUEUE_ORPHANED"


def test_stale_running_reconciliation_boundary() -> None:
    """12. Verifies that running runs within heartbeat timeout (<120s) are NOT reconciled."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    fresh_time = datetime.now(timezone.utc) - timedelta(seconds=30)

    with get_db_session() as session:
        run = EvalRun(
            run_id=run_id,
            job_id=job_id,
            status="running",
            created_at=fresh_time,
            started_at=fresh_time,
        )
        session.add(run)
        session.commit()

    reconciled = reconcile_stale_evaluations(heartbeat_timeout_seconds=120)
    assert len(reconciled) == 0

    with get_db_session() as session:
        rec = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        assert rec.status == "running"


def test_temporary_redis_disconnection_reconciliation() -> None:
    """13. Verifies that if Redis is offline during reconciliation sweep, DB state is NOT mutated."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    old_time = datetime.now(timezone.utc) - timedelta(seconds=200)

    with get_db_session() as session:
        run = EvalRun(
            run_id=run_id,
            job_id=job_id,
            status="running",
            created_at=old_time,
            started_at=old_time,
        )
        session.add(run)
        session.commit()

    mock_client = MagicMock()
    mock_client.ping.side_effect = redis.exceptions.ConnectionError("Redis down")

    reconciled = reconcile_stale_evaluations(redis_client=mock_client)
    assert reconciled == []

    # Database record was preserved as running (not mutated)
    with get_db_session() as session:
        rec = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        assert rec.status == "running"


def test_rq_registry_state_inspection() -> None:
    """14. Verifies that active jobs in StartedJobRegistry are NOT marked failed by reconciliation."""
    run_id, job_id = enqueue_evaluation_run(dataset_path=str(DATASET_PATH))

    # Move job into StartedJobRegistry
    client = get_redis_client()
    queue = Queue(settings.rq_queue_name, connection=client)
    started = StartedJobRegistry(queue=queue)
    client.zadd(started.key, {job_id: int(datetime.now(timezone.utc).timestamp()) + 300})

    # Set run to running with age > threshold
    old_time = datetime.now(timezone.utc) - timedelta(seconds=150)
    with get_db_session() as session:
        run = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        run.status = "running"
        run.started_at = old_time
        session.commit()

    # Sweep should see that job is in StartedJobRegistry and NOT mark it failed
    reconciled = reconcile_stale_evaluations(heartbeat_timeout_seconds=120)
    assert len(reconciled) == 0

    with get_db_session() as session:
        rec = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        assert rec.status == "running"


def test_idempotent_reconciliation() -> None:
    """15. Verifies that repeated reconciliation sweeps on the same state produce no errors or extra mutations."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    old_time = datetime.now(timezone.utc) - timedelta(seconds=100)

    with get_db_session() as session:
        run = EvalRun(run_id=run_id, job_id=job_id, status="queued", created_at=old_time)
        session.add(run)
        session.commit()

    # Sweep 1: reconciles
    first_pass = reconcile_stale_evaluations(stale_queued_seconds=60)
    assert len(first_pass) == 1

    # Sweep 2: no-op
    second_pass = reconcile_stale_evaluations(stale_queued_seconds=60)
    assert len(second_pass) == 0

    # Sweep 3: no-op
    third_pass = reconcile_stale_evaluations(stale_queued_seconds=60)
    assert len(third_pass) == 0


def test_kb_unavailability_aborts_evaluation() -> None:
    """16. Verifies Section 8: Evaluation runner aborts if required KB sections are missing, without mutating KB."""
    with get_db_session() as session:
        session.execute(text("TRUNCATE TABLE kb_sections CASCADE;"))
        session.commit()

    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    with get_db_session() as session:
        run = EvalRun(run_id=run_id, job_id=job_id, status="queued")
        session.add(run)
        session.commit()

    runner = EvaluationRunner()
    eval_run = asyncio.run(runner.run(dataset_path=DATASET_PATH, run_id=run_id))

    assert eval_run.status == "failed"
    assert eval_run.error_details["error_code"] == "KB_SECTIONS_UNAVAILABLE"

    # Confirms KB was NOT silently seeded
    with get_db_session() as session:
        count = session.scalar(select(func.count()).select_from(KBSection))
        assert count == 0


def test_single_active_run_constraint_enqueue() -> None:
    """17. Verifies P7-EC-002: Attempting to enqueue when another run is active raises ActiveEvaluationAlreadyRunningError."""
    run_id_1, job_id_1 = enqueue_evaluation_run(dataset_path=str(DATASET_PATH))

    with pytest.raises(ActiveEvaluationAlreadyRunningError) as exc_info:
        enqueue_evaluation_run(dataset_path=str(DATASET_PATH))

    assert "already active" in str(exc_info.value) or "queued or running" in str(exc_info.value)


def test_complete_evaluation_accounting_worker() -> None:
    """18. Verifies complete input accounting invariant (18 = 16 + 1 + 0 + 1) via worker execution."""
    run_id, job_id = enqueue_evaluation_run(dataset_path=str(DATASET_PATH))

    client = get_redis_client()
    queue = Queue(settings.rq_queue_name, connection=client)
    worker = SimpleWorker([queue], connection=client)
    worker.work(burst=True)

    with get_db_session() as session:
        eval_run = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()

        accounting = eval_run.metrics_summary["input_accounting"]
        assert accounting["total_lines"] == 18
        assert accounting["evaluated"] == 16
        assert accounting["inconclusive"] == 1
        assert accounting["invalid_input"] == 0
        assert accounting["model_failure"] == 1
        assert accounting["is_valid"] is True


def test_no_unauthorized_operational_actions_worker() -> None:
    """19. Verifies that the worker execution creates zero operational actions in PostgreSQL."""
    run_id, job_id = enqueue_evaluation_run(dataset_path=str(DATASET_PATH))

    client = get_redis_client()
    queue = Queue(settings.rq_queue_name, connection=client)
    worker = SimpleWorker([queue], connection=client)
    worker.work(burst=True)

    with get_db_session() as session:
        actions = session.execute(select(ProposedAction)).scalars().all()
        assert len(actions) == 0


def test_existing_cli_regression() -> None:
    """20. Verifies that existing standalone CLI execution continues to run smoothly."""
    import subprocess

    res = subprocess.run(
        [
            sys.executable,
            "-m",
            "trustdesk.eval.runner",
            "--eval-file",
            "./data/eval_cases.jsonl",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert res.returncode == 0
    assert "TRUSTDESK EVALUATION RUN REPORT" in res.stdout
    assert "Status:         COMPLETED" in res.stdout
    assert "Passed Cases:    9 / 18" in res.stdout
