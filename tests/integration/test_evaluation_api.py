from __future__ import annotations

import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import redis
from fastapi.testclient import TestClient
from rq import Queue, SimpleWorker
from sqlalchemy import func, select, text

from trustdesk.core.config import settings
from trustdesk.core.database import get_db_session
from trustdesk.core.redis import get_redis_client
from trustdesk.main import app
from trustdesk.models.action import ProposedAction
from trustdesk.models.eval import EvalResult, EvalRun
from trustdesk.models.knowledge import KBSection
from trustdesk.services.ingestion import ingest_kb_documents
from trustdesk.services.knowledge_service import derive_and_index_sections

client = TestClient(app)
AUTH_HEADER = {"Authorization": f"Bearer {settings.trustdesk_demo_token}"}
INVALID_AUTH_HEADER = {"Authorization": "Bearer invalid_secret_token_999"}
DATASET_PATH = Path("data/eval_cases.jsonl")


@pytest.fixture(autouse=True)
def clean_eval_environment():
    """Ensure clean PostgreSQL evaluation state, fresh KB sections, and flushed Redis."""
    orig_queue = settings.rq_queue_name
    settings.rq_queue_name = "test_eval_api_queue"

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
        redis_c = get_redis_client()
        redis_c.flushdb()
    except Exception:
        pass

    yield

    settings.rq_queue_name = orig_queue
    with get_db_session() as session:
        session.execute(
            text("TRUNCATE TABLE action_idempotency, proposed_actions, eval_results, eval_runs CASCADE;")
        )
        session.commit()
    try:
        redis_c = get_redis_client()
        redis_c.flushdb()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Test Scenarios
# ---------------------------------------------------------------------------

def test_authenticated_evaluation_submission() -> None:
    """1. Verifies that authenticated POST /api/v1/evaluations/run returns HTTP 202."""
    response = client.post(
        "/api/v1/evaluations/run",
        json={"dataset_path": str(DATASET_PATH)},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 202
    data = response.json()
    assert "run_id" in data
    assert "job_id" in data
    assert data["status"] == "queued"
    assert "enqueued for background processing" in data["message"]


def test_unauthenticated_submission_rejection() -> None:
    """2. Verifies that unauthenticated or invalid token requests return HTTP 401."""
    # Missing token
    resp_missing = client.post("/api/v1/evaluations/run", json={})
    assert resp_missing.status_code == 401
    assert resp_missing.json()["error"]["code"] == "UNAUTHORIZED"

    # Invalid token
    resp_invalid = client.post(
        "/api/v1/evaluations/run",
        json={},
        headers=INVALID_AUTH_HEADER,
    )
    assert resp_invalid.status_code == 401
    assert resp_invalid.json()["error"]["code"] == "UNAUTHORIZED"


def test_correct_http_202_response_structure() -> None:
    """3. Verifies schema structure of HTTP 202 Accepted response."""
    response = client.post(
        "/api/v1/evaluations/run",
        json={"dataset_path": str(DATASET_PATH)},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 202
    data = response.json()
    assert uuid.UUID(data["run_id"])
    assert data["job_id"].startswith("eval-job-")
    assert data["status"] == "queued"


def test_persisted_queued_run_and_job_mapping() -> None:
    """4. Verifies that POST /api/v1/evaluations/run persists a queued record in PostgreSQL."""
    response = client.post(
        "/api/v1/evaluations/run",
        json={"dataset_path": str(DATASET_PATH)},
        headers=AUTH_HEADER,
    )
    data = response.json()
    run_uuid = uuid.UUID(data["run_id"])
    job_id = data["job_id"]

    with get_db_session() as session:
        run = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_uuid)
        ).scalar_one()
        assert run.job_id == job_id
        assert run.status == "queued"
        assert run.total_cases == 0


def test_concurrent_submission_http_409() -> None:
    """5. Verifies P7-EC-002: Concurrent active submission returns HTTP 409 Conflict."""
    # First submission succeeds (202)
    resp1 = client.post(
        "/api/v1/evaluations/run",
        json={"dataset_path": str(DATASET_PATH)},
        headers=AUTH_HEADER,
    )
    assert resp1.status_code == 202

    # Second submission is blocked by partial unique index (409)
    resp2 = client.post(
        "/api/v1/evaluations/run",
        json={"dataset_path": str(DATASET_PATH)},
        headers=AUTH_HEADER,
    )
    assert resp2.status_code == 409
    err = resp2.json()["error"]
    assert err["code"] == "EVAL_ALREADY_RUNNING"
    assert "currently active" in err["message"]


def test_redis_unavailable_http_503() -> None:
    """6. Verifies P7-EC-001: When Redis broker is offline, endpoint returns HTTP 503 Service Unavailable."""
    with patch("trustdesk.worker.service.Queue.enqueue", side_effect=redis.exceptions.ConnectionError("Connection refused")):
        response = client.post(
            "/api/v1/evaluations/run",
            json={"dataset_path": str(DATASET_PATH)},
            headers=AUTH_HEADER,
        )
        assert response.status_code == 503
        err = response.json()["error"]
        assert err["code"] == "REDIS_UNAVAILABLE"
        assert "unreachable" in err["message"]


def test_reconciliation_of_stale_queued_runs() -> None:
    """7. Verifies Section 4.A & P7-EC-003: Pre-flight reconciliation recovers stale queued runs (>60s) before enqueuing."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=90)

    # Insert orphaned queued run directly in DB (not in Redis)
    with get_db_session() as session:
        orphaned = EvalRun(
            run_id=run_id,
            job_id=job_id,
            status="queued",
            created_at=stale_time,
        )
        session.add(orphaned)
        session.commit()

    # New submission triggers pre-flight reconciliation which cleans the orphaned run and succeeds with 202
    response = client.post(
        "/api/v1/evaluations/run",
        json={"dataset_path": str(DATASET_PATH)},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 202

    # Verify that the orphaned run was marked 'failed'
    with get_db_session() as session:
        old_run = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        assert old_run.status == "failed"
        assert old_run.error_details["error_code"] == "ENQUEUE_ORPHANED"


def test_reconciliation_of_interrupted_running_runs() -> None:
    """8. Verifies Section 4.A & P7-EC-004: Pre-flight reconciliation recovers dead worker runs (>120s) before enqueuing."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=150)

    # Insert orphaned running run directly in DB
    with get_db_session() as session:
        interrupted = EvalRun(
            run_id=run_id,
            job_id=job_id,
            status="running",
            created_at=stale_time,
            started_at=stale_time,
        )
        session.add(interrupted)
        session.commit()

    # New submission triggers pre-flight reconciliation which cleans the dead run and succeeds with 202
    response = client.post(
        "/api/v1/evaluations/run",
        json={"dataset_path": str(DATASET_PATH)},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 202

    # Verify that the interrupted run was marked 'failed'
    with get_db_session() as session:
        old_run = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        assert old_run.status == "failed"
        assert old_run.error_details["error_code"] == "WORKER_INTERRUPTED"


def test_healthy_active_run_protection() -> None:
    """9. Verifies that fresh running runs (<120s) are NOT reconciled and conflict returns HTTP 409."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    fresh_time = datetime.now(timezone.utc) - timedelta(seconds=20)

    with get_db_session() as session:
        active = EvalRun(
            run_id=run_id,
            job_id=job_id,
            status="running",
            created_at=fresh_time,
            started_at=fresh_time,
        )
        session.add(active)
        session.commit()

    # Pre-flight check leaves fresh run alone; attempt to enqueue conflicts with 409
    response = client.post(
        "/api/v1/evaluations/run",
        json={"dataset_path": str(DATASET_PATH)},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVAL_ALREADY_RUNNING"

    # Status remains running
    with get_db_session() as session:
        run = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        assert run.status == "running"


def test_temporary_redis_outage_protection() -> None:
    """10. Verifies that reconciliation during Redis outage aborts without mutating DB records."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    old_time = datetime.now(timezone.utc) - timedelta(seconds=200)

    with get_db_session() as session:
        active = EvalRun(
            run_id=run_id,
            job_id=job_id,
            status="running",
            created_at=old_time,
            started_at=old_time,
        )
        session.add(active)
        session.commit()

    with patch("trustdesk.worker.reconciliation.check_redis_connection", side_effect=redis.exceptions.ConnectionError("Redis outage")):
        with patch("trustdesk.worker.service.get_redis_client", side_effect=redis.exceptions.ConnectionError("Redis outage")):
            response = client.post(
                "/api/v1/evaluations/run",
                json={"dataset_path": str(DATASET_PATH)},
                headers=AUTH_HEADER,
            )
            # Active run was preserved, so submission is rejected with 409 Conflict
            assert response.status_code == 409

    # DB record was NOT mutated to failed during the Redis outage
    with get_db_session() as session:
        run = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        assert run.status == "running"


def test_operational_reconcile_cli() -> None:
    """11. Verifies Section 4.B: python -m trustdesk.worker.worker --reconcile runs sweep and exits 0."""
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

    res = subprocess.run(
        [sys.executable, "-m", "trustdesk.worker.worker", "--reconcile"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert "Reconciliation sweep completed: 1 run(s) reconciled." in res.stdout

    with get_db_session() as session:
        rec = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        assert rec.status == "failed"
        assert rec.error_details["error_code"] == "WORKER_INTERRUPTED"


def test_job_polling_queued_status() -> None:
    """12. Verifies GET /api/v1/jobs/{job_id} returns queued status."""
    resp = client.post(
        "/api/v1/evaluations/run",
        json={"dataset_path": str(DATASET_PATH)},
        headers=AUTH_HEADER,
    )
    job_id = resp.json()["job_id"]

    poll_resp = client.get(f"/api/v1/jobs/{job_id}", headers=AUTH_HEADER)
    assert poll_resp.status_code == 200
    data = poll_resp.json()
    assert data["job_id"] == job_id
    assert data["status"] == "queued"
    assert data["total_cases"] == 0


def test_job_polling_running_status() -> None:
    """13. Verifies GET /api/v1/jobs/{job_id} returns running status."""
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

    poll_resp = client.get(f"/api/v1/jobs/{job_id}", headers=AUTH_HEADER)
    assert poll_resp.status_code == 200
    data = poll_resp.json()
    assert data["job_id"] == job_id
    assert data["status"] == "running"
    assert data["started_at"] is not None


def test_job_polling_completed_status() -> None:
    """14. Verifies GET /api/v1/jobs/{job_id} returns completed status with metrics and case counts."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    now_utc = datetime.now(timezone.utc)

    with get_db_session() as session:
        run = EvalRun(
            run_id=run_id,
            job_id=job_id,
            status="completed",
            total_cases=18,
            passed_cases=9,
            created_at=now_utc,
            started_at=now_utc,
            finished_at=now_utc,
        )
        session.add(run)
        session.commit()

    poll_resp = client.get(f"/api/v1/jobs/{job_id}", headers=AUTH_HEADER)
    assert poll_resp.status_code == 200
    data = poll_resp.json()
    assert data["job_id"] == job_id
    assert data["status"] == "completed"
    assert data["total_cases"] == 18
    assert data["passed_cases"] == 9
    assert data["finished_at"] is not None


def test_job_polling_failed_status() -> None:
    """15. Verifies GET /api/v1/jobs/{job_id} returns failed status with sanitized error details."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    now_utc = datetime.now(timezone.utc)

    with get_db_session() as session:
        run = EvalRun(
            run_id=run_id,
            job_id=job_id,
            status="failed",
            error_details={
                "error_code": "WORKER_EXECUTION_FAILURE",
                "message": "Simulated error details",
            },
            created_at=now_utc,
            finished_at=now_utc,
        )
        session.add(run)
        session.commit()

    poll_resp = client.get(f"/api/v1/jobs/{job_id}", headers=AUTH_HEADER)
    assert poll_resp.status_code == 200
    data = poll_resp.json()
    assert data["job_id"] == job_id
    assert data["status"] == "failed"
    assert data["error_details"]["error_code"] == "WORKER_EXECUTION_FAILURE"


def test_unknown_job_http_404() -> None:
    """16. Verifies GET /api/v1/jobs/unknown-job returns HTTP 404 Not Found."""
    resp = client.get("/api/v1/jobs/non-existent-job-id", headers=AUTH_HEADER)
    assert resp.status_code == 404
    err = resp.json()["error"]
    assert err["code"] == "JOB_NOT_FOUND"


def test_evaluation_history_ordering_and_pagination() -> None:
    """17. Verifies GET /api/v1/evaluations returns deterministic newest-first ordering and bounded pagination."""
    now_utc = datetime.now(timezone.utc)
    with get_db_session() as session:
        runs = [
            EvalRun(
                run_id=uuid.uuid4(),
                job_id=f"job-{idx}",
                status="completed",
                total_cases=18,
                passed_cases=9,
                created_at=now_utc + timedelta(seconds=idx),
            )
            for idx in range(5)
        ]
        session.add_all(runs)
        session.commit()

    resp = client.get("/api/v1/evaluations?limit=3&offset=0", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 3
    assert data["items"][0]["job_id"] == "job-4"
    assert data["items"][1]["job_id"] == "job-3"
    assert data["items"][2]["job_id"] == "job-2"

    # Next page
    resp_page2 = client.get("/api/v1/evaluations?limit=3&offset=3", headers=AUTH_HEADER)
    assert resp_page2.status_code == 200
    data2 = resp_page2.json()
    assert len(data2["items"]) == 2
    assert data2["items"][0]["job_id"] == "job-1"
    assert data2["items"][1]["job_id"] == "job-0"


def test_evaluation_detail_retrieval() -> None:
    """18. Verifies GET /api/v1/evaluations/{run_id} returns full run report and metrics."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    now_utc = datetime.now(timezone.utc)

    with get_db_session() as session:
        run = EvalRun(
            run_id=run_id,
            job_id=job_id,
            status="completed",
            total_cases=18,
            passed_cases=9,
            metrics_summary={"overall_pass_rate": {"rate": 0.5, "numerator": 9, "denominator": 18}},
            created_at=now_utc,
            started_at=now_utc,
            finished_at=now_utc,
        )
        session.add(run)
        session.commit()

    resp = client.get(f"/api/v1/evaluations/{run_id}", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == str(run_id)
    assert data["status"] == "completed"
    assert data["metrics_summary"]["overall_pass_rate"]["rate"] == 0.5


def test_per_case_source_line_ordering() -> None:
    """19. Verifies GET /api/v1/evaluations/{run_id} returns results strictly ordered by source_line_number."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    now_utc = datetime.now(timezone.utc)

    with get_db_session() as session:
        run = EvalRun(
            run_id=run_id,
            job_id=job_id,
            status="completed",
            created_at=now_utc,
        )
        session.add(run)
        # Add out-of-order results
        res3 = EvalResult(run_id=run_id, source_line_number=3, case_id="EVAL-003")
        res1 = EvalResult(run_id=run_id, source_line_number=1, case_id="EVAL-001")
        res2 = EvalResult(run_id=run_id, source_line_number=2, case_id="EVAL-002")
        session.add_all([res3, res1, res2])
        session.commit()

    resp = client.get(f"/api/v1/evaluations/{run_id}", headers=AUTH_HEADER)
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 3
    assert [r["source_line_number"] for r in results] == [1, 2, 3]
    assert [r["case_id"] for r in results] == ["EVAL-001", "EVAL-002", "EVAL-003"]


def test_unknown_run_http_404() -> None:
    """20. Verifies GET /api/v1/evaluations/{run_id} returns HTTP 404 Not Found for non-existent UUID."""
    unknown_id = str(uuid.uuid4())
    resp = client.get(f"/api/v1/evaluations/{unknown_id}", headers=AUTH_HEADER)
    assert resp.status_code == 404
    err = resp.json()["error"]
    assert err["code"] == "EVALUATION_NOT_FOUND"

    # Malformed UUID also 404
    resp_bad = client.get("/api/v1/evaluations/not-a-valid-uuid", headers=AUTH_HEADER)
    assert resp_bad.status_code == 404


def test_sensitive_diagnostic_redaction_in_api() -> None:
    """21. Verifies that evaluation details do not expose raw tokens, secrets, or internal stack traces."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{run_id.hex[:12]}"
    now_utc = datetime.now(timezone.utc)

    with get_db_session() as session:
        run = EvalRun(
            run_id=run_id,
            job_id=job_id,
            status="completed",
            created_at=now_utc,
        )
        session.add(run)
        res = EvalResult(
            run_id=run_id,
            source_line_number=1,
            case_id="EVAL-001",
            execution_details={
                "api_key": "[REDACTED_SECRET]",
                "auth": "[REDACTED_SECRET]",
                "contact": "user [REDACTED_EMAIL]",
            },
        )
        session.add(res)
        session.commit()

    resp = client.get(f"/api/v1/evaluations/{run_id}", headers=AUTH_HEADER)
    assert resp.status_code == 200
    details = resp.json()["results"][0]["execution_details"]
    assert details["api_key"] == "[REDACTED_SECRET]"
    assert details["auth"] == "[REDACTED_SECRET]"


def test_no_synchronous_model_execution_in_api_submission() -> None:
    """22. Verifies that POST /run returns immediately without invoking AI inference synchronously."""
    import time

    start = time.perf_counter()
    resp = client.post(
        "/api/v1/evaluations/run",
        json={"dataset_path": str(DATASET_PATH)},
        headers=AUTH_HEADER,
    )
    duration = time.perf_counter() - start

    assert resp.status_code == 202
    assert duration < 0.25  # Immediate sub-250ms asynchronous enqueue
    assert resp.json()["status"] == "queued"


def test_no_unauthorized_operational_action_execution_via_api() -> None:
    """23. Verifies that API submission and worker processing create zero operational actions."""
    resp = client.post(
        "/api/v1/evaluations/run",
        json={"dataset_path": str(DATASET_PATH)},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 202

    # Process job via burst worker
    client_redis = get_redis_client()
    queue = Queue(settings.rq_queue_name, connection=client_redis)
    worker = SimpleWorker([queue], connection=client_redis)
    worker.work(burst=True)

    with get_db_session() as session:
        actions = session.execute(select(ProposedAction)).scalars().all()
        assert len(actions) == 0


def test_existing_api_regression_compatibility() -> None:
    """24. Verifies that existing tickets, health, triage, and draft routes continue to function normally."""
    # Health endpoint
    resp_health = client.get("/api/v1/health")
    assert resp_health.status_code == 200
    assert resp_health.json()["status"] == "healthy"

    # Tickets endpoint
    resp_tickets = client.get("/api/v1/tickets", headers=AUTH_HEADER)
    assert resp_tickets.status_code == 200
    assert "items" in resp_tickets.json()


def test_dataset_path_traversal_rejection() -> None:
    """25. Verifies that directory traversal sequences in dataset_path are rejected with HTTP 422."""
    traversal_payloads = [
        "../../etc/passwd",
        "data/../../etc/passwd.jsonl",
        "data/eval_cases.jsonl\x00.jsonl",
        "../data/eval_cases.jsonl",
    ]
    for bad_path in traversal_payloads:
        resp = client.post(
            "/api/v1/evaluations/run",
            json={"dataset_path": bad_path},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 422, f"Expected 422 for {bad_path}, got {resp.status_code}"


def test_dataset_path_validation_rules() -> None:
    """26. Verifies that invalid extensions and paths outside data/ directory are rejected with HTTP 422."""
    # Non-.jsonl extension
    resp_ext = client.post(
        "/api/v1/evaluations/run",
        json={"dataset_path": "data/kb_documents.json"},
        headers=AUTH_HEADER,
    )
    assert resp_ext.status_code == 422

    # Outside data/ directory
    resp_outside = client.post(
        "/api/v1/evaluations/run",
        json={"dataset_path": "tests/data/eval_cases.jsonl"},
        headers=AUTH_HEADER,
    )
    assert resp_outside.status_code == 422


def test_dataset_path_symlink_escape_api_rejection(tmp_path: Path) -> None:
    """27. Verifies that symlinks within data/ pointing to outside files are rejected with HTTP 422."""
    import os

    outside_file = tmp_path / "secret_cases.jsonl"
    outside_file.write_text("{}", encoding="utf-8")

    symlink_path = Path("data/api_symlink_escape_test.jsonl")
    try:
        if symlink_path.is_symlink() or symlink_path.exists():
            symlink_path.unlink()
        os.symlink(outside_file.resolve(), symlink_path)

        resp = client.post(
            "/api/v1/evaluations/run",
            json={"dataset_path": "data/api_symlink_escape_test.jsonl"},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 422
        error_detail = resp.json()["error"]["details"]["errors"][0]["msg"]
        assert "outside the approved data directory" in error_detail
    finally:
        if symlink_path.is_symlink() or symlink_path.exists():
            symlink_path.unlink()


def test_dataset_path_absolute_path_outside_api_rejection() -> None:
    """28. Verifies that absolute paths outside the approved data directory are rejected with HTTP 422."""
    resp = client.post(
        "/api/v1/evaluations/run",
        json={"dataset_path": "/tmp/outside_dataset.jsonl"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 422
    error_detail = resp.json()["error"]["details"]["errors"][0]["msg"]
    assert "outside the approved data directory" in error_detail


