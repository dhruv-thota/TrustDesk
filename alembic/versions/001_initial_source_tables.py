"""create initial source tables

Revision ID: 001_initial_source_tables
Revises:
Create Date: 2026-11-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial_source_tables"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. customers table
    op.create_table(
        "customers",
        sa.Column("customer_id", sa.String(length=64), primary_key=True, comment="Original unique dataset identifier"),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 2. orders table
    op.create_table(
        "orders",
        sa.Column("order_id", sa.String(length=64), primary_key=True, comment="Original unique dataset order identifier"),
        sa.Column("customer_id", sa.String(length=64), nullable=False),
        sa.Column("order_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("total_amount", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("items", postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"), nullable=True),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.customer_id"],
            name="fk_orders_customer_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_orders_customer_id", "orders", ["customer_id"], unique=False)

    # 3. tickets table
    op.create_table(
        "tickets",
        sa.Column("ticket_id", sa.String(length=64), primary_key=True, comment="Original unique dataset ticket identifier"),
        sa.Column("customer_id", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="open", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Authoritative evaluation timestamp"),
        sa.Column("raw_metadata", postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"), server_default=sa.text("'{}'"), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.customer_id"],
            name="fk_tickets_customer_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.order_id"],
            name="fk_tickets_order_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("idx_tickets_customer_id", "tickets", ["customer_id"], unique=False)
    op.create_index("idx_tickets_order_id", "tickets", ["order_id"], unique=False)

    # 4. kb_documents table
    op.create_table(
        "kb_documents",
        sa.Column("kb_id", sa.String(length=64), primary_key=True, comment="Original dataset document identifier"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 5. quarantined_records table
    op.create_table(
        "quarantined_records",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("record_type", sa.String(length=32), nullable=False),
        sa.Column("record_id", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_quarantined_record_id", "quarantined_records", ["record_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_quarantined_record_id", table_name="quarantined_records")
    op.drop_table("quarantined_records")
    op.drop_table("kb_documents")
    op.drop_index("idx_tickets_order_id", table_name="tickets")
    op.drop_index("idx_tickets_customer_id", table_name="tickets")
    op.drop_table("tickets")
    op.drop_index("idx_orders_customer_id", table_name="orders")
    op.drop_table("orders")
    op.drop_table("customers")

