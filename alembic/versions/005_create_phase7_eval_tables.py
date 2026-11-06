"""create phase 7 eval tables: eval_runs, eval_results

Revision ID: 005_create_phase7_eval_tables
Revises: 004_create_phase5_action_tables
Create Date: 2026-11-05 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005_create_phase7_eval_tables"
down_revision: Union[str, None] = "004_create_phase5_action_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. eval_runs
    op.create_table(
        "eval_runs",
        sa.Column(
            "run_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column(
            "total_cases",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "passed_cases",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "metrics_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "error_details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_eval_runs_job_id", "eval_runs", ["job_id"], unique=True)
    op.create_index("idx_eval_runs_status", "eval_runs", ["status"], unique=False)
    op.create_index("idx_eval_runs_created_at", "eval_runs", ["created_at"], unique=False)

    # Partial unique index enforcing exactly one active eval run (queued or running)
    op.create_index(
        "idx_single_active_eval_run",
        "eval_runs",
        [sa.text("(1)")],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    # 2. eval_results
    op.create_table(
        "eval_results",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("source_line_number", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=True),
        sa.Column("ticket_id", sa.String(length=64), nullable=True),
        sa.Column(
            "validation_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'valid'"),
        ),
        sa.Column(
            "triage_passed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "citation_passed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "safety_passed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "escalation_passed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "execution_details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["eval_runs.run_id"],
            name="fk_eval_results_run_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "run_id",
            "source_line_number",
            name="uq_eval_results_run_line",
        ),
    )
    op.create_index("idx_eval_results_run_id", "eval_results", ["run_id"], unique=False)
    op.create_index(
        "idx_eval_results_run_status",
        "eval_results",
        ["run_id", "validation_status"],
        unique=False,
    )
    op.create_index("idx_eval_results_case_id", "eval_results", ["case_id"], unique=False)

    # Partial unique index enforcing unique case_id per run when case_id is not null
    op.create_index(
        "idx_unique_valid_run_case",
        "eval_results",
        ["run_id", "case_id"],
        unique=True,
        postgresql_where=sa.text("case_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_unique_valid_run_case",
        table_name="eval_results",
        postgresql_where=sa.text("case_id IS NOT NULL"),
    )
    op.drop_index("idx_eval_results_case_id", table_name="eval_results")
    op.drop_index("idx_eval_results_run_status", table_name="eval_results")
    op.drop_index("idx_eval_results_run_id", table_name="eval_results")
    op.drop_table("eval_results")

    op.drop_index(
        "idx_single_active_eval_run",
        table_name="eval_runs",
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.drop_index("idx_eval_runs_created_at", table_name="eval_runs")
    op.drop_index("idx_eval_runs_status", table_name="eval_runs")
    op.drop_index("idx_eval_runs_job_id", table_name="eval_runs")
    op.drop_table("eval_runs")

