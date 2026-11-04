"""create phase 4 tables: triage_results, draft_responses, draft_citations, execution_traces

Revision ID: 003_create_phase4_tables
Revises: 002_create_kb_sections_fts
Create Date: 2026-11-03 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003_create_phase4_tables"
down_revision: Union[str, None] = "002_create_kb_sections_fts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. triage_results
    op.create_table(
        "triage_results",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("ticket_id", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("needs_escalation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("is_fallback", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "sanitized_diagnostics",
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
            ["ticket_id"],
            ["tickets.ticket_id"],
            name="fk_triage_results_ticket_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_triage_results_ticket_id", "triage_results", ["ticket_id"], unique=False)

    # 2. draft_responses
    op.create_table(
        "draft_responses",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("ticket_id", sa.String(length=64), nullable=False),
        sa.Column("draft_text", sa.Text(), nullable=False),
        sa.Column("has_valid_provenance", sa.Boolean(), nullable=False),
        sa.Column("is_grounded", sa.Boolean(), nullable=False),
        sa.Column("escalation_suggested", sa.Boolean(), nullable=False),
        sa.Column("escalation_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.ticket_id"],
            name="fk_draft_responses_ticket_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_draft_responses_ticket_id", "draft_responses", ["ticket_id"], unique=False)

    # 3. draft_citations
    op.create_table(
        "draft_citations",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("draft_id", sa.UUID(), nullable=False),
        sa.Column("kb_id", sa.String(length=64), nullable=False),
        sa.Column("section_id", sa.String(length=128), nullable=False),
        sa.Column("quoted_snippet", sa.Text(), nullable=True),
        sa.Column("is_valid_provenance", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(
            ["draft_id"],
            ["draft_responses.id"],
            name="fk_draft_citations_draft_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_draft_citations_draft_id", "draft_citations", ["draft_id"], unique=False)
    op.create_index("idx_draft_citations_section_id", "draft_citations", ["section_id"], unique=False)

    # 4. execution_traces
    op.create_table(
        "execution_traces",
        sa.Column(
            "trace_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("ticket_id", sa.String(length=64), nullable=False),
        sa.Column("run_type", sa.String(length=32), nullable=False),
        sa.Column(
            "retrieved_kb_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "proposed_actions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "executed_actions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("guardrail_outcome", sa.String(length=32), nullable=False, server_default=sa.text("'passed'")),
        sa.Column("final_status", sa.String(length=32), nullable=False),
        sa.Column(
            "sanitized_telemetry",
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
            ["ticket_id"],
            ["tickets.ticket_id"],
            name="fk_execution_traces_ticket_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_execution_traces_ticket_id", "execution_traces", ["ticket_id"], unique=False)
    op.create_index("idx_execution_traces_run_type", "execution_traces", ["run_type"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_execution_traces_run_type", table_name="execution_traces")
    op.drop_index("idx_execution_traces_ticket_id", table_name="execution_traces")
    op.drop_table("execution_traces")

    op.drop_index("idx_draft_citations_section_id", table_name="draft_citations")
    op.drop_index("idx_draft_citations_draft_id", table_name="draft_citations")
    op.drop_table("draft_citations")

    op.drop_index("idx_draft_responses_ticket_id", table_name="draft_responses")
    op.drop_table("draft_responses")

    op.drop_index("idx_triage_results_ticket_id", table_name="triage_results")
    op.drop_table("triage_results")
