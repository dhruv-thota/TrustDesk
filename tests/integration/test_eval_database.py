from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from trustdesk.core.config import settings
from trustdesk.core.database import Base, engine, get_db_session
from trustdesk.models.eval import EvalResult, EvalRun


@pytest.fixture(autouse=True)
def clean_eval_tables():
    """Ensure eval tables are clean before and after each test."""
    with get_db_session() as session:
        session.execute(text("TRUNCATE TABLE eval_results, eval_runs CASCADE;"))
        session.commit()
    yield
    with get_db_session() as session:
        session.execute(text("TRUNCATE TABLE eval_results, eval_runs CASCADE;"))
        session.commit()


def test_schema_eval_tables_exist() -> None:
    """Verifies eval_runs and eval_results exist in schema with expected columns and primary keys."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    assert "eval_runs" in existing_tables, "Table 'eval_runs' missing from database schema"
    assert "eval_results" in existing_tables, "Table 'eval_results' missing from database schema"

    # Verify primary keys
    assert inspector.get_pk_constraint("eval_runs")["constrained_columns"] == ["run_id"]
    assert inspector.get_pk_constraint("eval_results")["constrained_columns"] == ["id"]

    # Verify foreign keys
    eval_results_fks = inspector.get_foreign_keys("eval_results")
    assert any(
        fk["referred_table"] == "eval_runs"
        and fk["referred_columns"] == ["run_id"]
        and fk["constrained_columns"] == ["run_id"]
        for fk in eval_results_fks
    ), "Foreign key from eval_results.run_id to eval_runs.run_id missing"


def test_eval_run_and_result_persistence_and_cascade() -> None:
    """Verifies creating an EvalRun, adding EvalResult, querying, and cascade deletion."""
    run_id = uuid.uuid4()
    job_id = f"eval-job-{uuid.uuid4().hex[:8]}"

    with get_db_session() as session:
        run = EvalRun(
            run_id=run_id,
            job_id=job_id,
            status="queued",
            total_cases=18,
            passed_cases=0,
            metrics_summary={"triage_accuracy": 0.0},
            error_details=None,
        )
        session.add(run)
        session.commit()

    with get_db_session() as session:
        saved_run = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        assert saved_run.status == "queued"
        assert saved_run.total_cases == 18
        assert saved_run.metrics_summary == {"triage_accuracy": 0.0}
        assert saved_run.created_at is not None

        result_id = uuid.uuid4()
        result = EvalResult(
            id=result_id,
            run_id=run_id,
            source_line_number=1,
            case_id="EVAL-001",
            ticket_id="TIK-001",
            validation_status="valid",
            triage_passed=True,
            citation_passed=True,
            safety_passed=True,
            escalation_passed=True,
            execution_details={"latency_ms": 120},
        )
        session.add(result)
        session.commit()

    # Query relationship and result fields
    with get_db_session() as session:
        loaded_run = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        assert len(loaded_run.results) == 1
        assert loaded_run.results[0].case_id == "EVAL-001"
        assert loaded_run.results[0].execution_details == {"latency_ms": 120}

    # Verify ON DELETE CASCADE
    with get_db_session() as session:
        run_to_delete = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        session.delete(run_to_delete)
        session.commit()

    with get_db_session() as session:
        remaining_results = session.execute(
            select(EvalResult).where(EvalResult.run_id == run_id)
        ).scalars().all()
        assert len(remaining_results) == 0


def test_single_active_eval_run_constraint() -> None:
    """Verifies that partial unique index idx_single_active_eval_run allows only one active run."""
    with get_db_session() as session:
        first_run = EvalRun(
            run_id=uuid.uuid4(),
            job_id=f"job-{uuid.uuid4().hex[:8]}",
            status="queued",
        )
        session.add(first_run)
        session.commit()

    # Attempting to insert another 'queued' run must raise IntegrityError
    with pytest.raises(IntegrityError):
        with get_db_session() as session:
            second_run = EvalRun(
                run_id=uuid.uuid4(),
                job_id=f"job-{uuid.uuid4().hex[:8]}",
                status="queued",
            )
            session.add(second_run)
            session.commit()

    # Attempting to insert a 'running' run must also raise IntegrityError
    with pytest.raises(IntegrityError):
        with get_db_session() as session:
            running_run = EvalRun(
                run_id=uuid.uuid4(),
                job_id=f"job-{uuid.uuid4().hex[:8]}",
                status="running",
            )
            session.add(running_run)
            session.commit()

    # Transitioning the active run to 'completed' frees the slot
    with get_db_session() as session:
        run = session.execute(select(EvalRun)).scalar_one()
        run.status = "completed"
        session.commit()

    # Now a new 'queued' run succeeds
    second_id = uuid.uuid4()
    with get_db_session() as session:
        new_run = EvalRun(
            run_id=second_id,
            job_id=f"job-{uuid.uuid4().hex[:8]}",
            status="queued",
        )
        session.add(new_run)
        session.commit()

    # Transitioning to 'failed' also frees the slot
    with get_db_session() as session:
        run = session.execute(select(EvalRun).where(EvalRun.run_id == second_id)).scalar_one()
        run.status = "failed"
        session.commit()

    # Another 'running' run succeeds
    with get_db_session() as session:
        third_run = EvalRun(
            run_id=uuid.uuid4(),
            job_id=f"job-{uuid.uuid4().hex[:8]}",
            status="running",
        )
        session.add(third_run)
        session.commit()


def test_eval_result_source_line_uniqueness() -> None:
    """Verifies that uq_eval_results_run_line prevents duplicate source_line_number per run."""
    run_id = uuid.uuid4()
    with get_db_session() as session:
        run = EvalRun(
            run_id=run_id,
            job_id=f"job-{uuid.uuid4().hex[:8]}",
            status="queued",
        )
        session.add(run)
        session.commit()

    with get_db_session() as session:
        res1 = EvalResult(
            run_id=run_id,
            source_line_number=1,
            case_id="EVAL-001",
        )
        session.add(res1)
        session.commit()

    # Duplicate source_line_number in same run fails
    with pytest.raises(IntegrityError):
        with get_db_session() as session:
            res2 = EvalResult(
                run_id=run_id,
                source_line_number=1,
                case_id="EVAL-002",
            )
            session.add(res2)
            session.commit()

    # Distinct source_line_number succeeds
    with get_db_session() as session:
        res3 = EvalResult(
            run_id=run_id,
            source_line_number=2,
            case_id="EVAL-002",
        )
        session.add(res3)
        session.commit()


def test_eval_result_valid_case_id_uniqueness() -> None:
    """Verifies that idx_unique_valid_run_case prevents duplicate non-null case_id per run."""
    run1_id = uuid.uuid4()
    run2_id = uuid.uuid4()

    with get_db_session() as session:
        run1 = EvalRun(
            run_id=run1_id,
            job_id=f"job-{uuid.uuid4().hex[:8]}",
            status="completed",
        )
        run2 = EvalRun(
            run_id=run2_id,
            job_id=f"job-{uuid.uuid4().hex[:8]}",
            status="failed",
        )
        session.add_all([run1, run2])
        session.commit()

    with get_db_session() as session:
        res1 = EvalResult(
            run_id=run1_id,
            source_line_number=1,
            case_id="EVAL-001",
        )
        session.add(res1)
        session.commit()

    # Duplicate case_id within run1 fails (even with different source_line_number)
    with pytest.raises(IntegrityError):
        with get_db_session() as session:
            res2 = EvalResult(
                run_id=run1_id,
                source_line_number=2,
                case_id="EVAL-001",
            )
            session.add(res2)
            session.commit()

    # Same case_id in run2 succeeds (uniqueness is scoped per run)
    with get_db_session() as session:
        res_run2 = EvalResult(
            run_id=run2_id,
            source_line_number=1,
            case_id="EVAL-001",
        )
        session.add(res_run2)
        session.commit()


def test_eval_result_multiple_malformed_lines_null_case_id() -> None:
    """Verifies that multiple lines with null case_id can coexist in the same run."""
    run_id = uuid.uuid4()
    with get_db_session() as session:
        run = EvalRun(
            run_id=run_id,
            job_id=f"job-{uuid.uuid4().hex[:8]}",
            status="queued",
        )
        session.add(run)
        session.commit()

    # Multiple records with case_id=None are allowed by the partial unique index
    with get_db_session() as session:
        res1 = EvalResult(
            run_id=run_id,
            source_line_number=1,
            case_id=None,
            validation_status="malformed_input",
            execution_details={"error": "JSON parse error"},
        )
        res2 = EvalResult(
            run_id=run_id,
            source_line_number=2,
            case_id=None,
            validation_status="malformed_input",
            execution_details={"error": "Missing expected fields"},
        )
        session.add_all([res1, res2])
        session.commit()

    with get_db_session() as session:
        saved = session.execute(
            select(EvalResult).where(EvalResult.run_id == run_id)
        ).scalars().all()
        assert len(saved) == 2
        assert all(r.case_id is None for r in saved)
        assert {r.source_line_number for r in saved} == {1, 2}


def test_migration_005_downgrade_and_reupgrade() -> None:
    """Verifies that Alembic migration 005 downgrades cleanly to 004 and re-upgrades to head."""
    project_root = Path(__file__).resolve().parent.parent.parent
    alembic_ini = project_root / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url_test)

    # Downgrade to 004_create_phase5_action_tables
    command.downgrade(alembic_cfg, "004_create_phase5_action_tables")

    inspector = inspect(engine)
    downgraded_tables = set(inspector.get_table_names())
    assert "eval_runs" not in downgraded_tables
    assert "eval_results" not in downgraded_tables
    # Phase 1-5 tables remain intact
    assert "tickets" in downgraded_tables
    assert "proposed_actions" in downgraded_tables
    assert "action_idempotency" in downgraded_tables

    # Re-upgrade to head (005_create_phase7_eval_tables)
    command.upgrade(alembic_cfg, "head")

    inspector_after = inspect(engine)
    reupgraded_tables = set(inspector_after.get_table_names())
    assert "eval_runs" in reupgraded_tables
    assert "eval_results" in reupgraded_tables

