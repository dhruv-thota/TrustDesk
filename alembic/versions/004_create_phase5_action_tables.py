"""create phase 5 action tables: proposed_actions, action_idempotency

Revision ID: 004_create_phase5_action_tables
Revises: 003_create_phase4_tables
Create Date: 2026-11-04 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004_create_phase5_action_tables"
down_revision: Union[str, None] = "003_create_phase4_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. proposed_actions
    op.create_table(
        "proposed_actions",
        sa.Column(
            "action_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("ticket_id", sa.String(length=64), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'pending_approval'")),
        sa.Column(
            "action_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("proposed_by", sa.String(length=32), nullable=False, server_default=sa.text("'ai'")),
        sa.Column("reviewed_by", sa.String(length=64), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.ticket_id"],
            name="fk_proposed_actions_ticket_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_proposed_actions_ticket_id", "proposed_actions", ["ticket_id"], unique=False)

    # Approved partial unique index for U-001: exactly one active (pending or executed) refund review per ticket
    op.create_index(
        "idx_unique_active_refund_review",
        "proposed_actions",
        ["ticket_id", "action_type"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending_approval', 'executed')"),
    )

    # 2. action_idempotency
    op.create_table(
        "action_idempotency",
        sa.Column("idempotency_key", sa.String(length=128), primary_key=True, nullable=False),
        sa.Column("action_id", sa.UUID(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "response_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["proposed_actions.action_id"],
            name="fk_action_idempotency_action_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_action_idempotency_action_id", "action_idempotency", ["action_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_action_idempotency_action_id", table_name="action_idempotency")
    op.drop_table("action_idempotency")
    op.drop_index("idx_unique_active_refund_review", table_name="proposed_actions")
    op.drop_index("idx_proposed_actions_ticket_id", table_name="proposed_actions")
    op.drop_table("proposed_actions")

