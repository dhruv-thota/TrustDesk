"""create kb_sections table with full-text search GIN index

Revision ID: 002_create_kb_sections_fts
Revises: 001_initial_source_tables
Create Date: 2026-11-03 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002_create_kb_sections_fts"
down_revision: Union[str, None] = "001_initial_source_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kb_sections",
        sa.Column(
            "section_id",
            sa.String(length=128),
            primary_key=True,
            comment="Deterministic section reference formatted as {kb_id}#sec-{index}",
        ),
        sa.Column("kb_id", sa.String(length=64), nullable=False),
        sa.Column("section_index", sa.Integer(), nullable=False),
        sa.Column("section_title", sa.String(length=255), nullable=False),
        sa.Column("section_content", sa.Text(), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('english', coalesce(section_title, '')), 'A') || "
                "setweight(to_tsvector('english', coalesce(section_content, '')), 'B')",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["kb_id"],
            ["kb_documents.kb_id"],
            name="fk_kb_sections_kb_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_kb_sections_kb_id", "kb_sections", ["kb_id"], unique=False)
    op.create_index(
        "idx_kb_sections_fts",
        "kb_sections",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("idx_kb_sections_fts", table_name="kb_sections", postgresql_using="gin")
    op.drop_index("idx_kb_sections_kb_id", table_name="kb_sections")
    op.drop_table("kb_sections")

