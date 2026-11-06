from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from trustdesk.core.database import Base


class EvalRun(Base):
    """Authoritative durable record of an evaluation execution run."""

    __tablename__ = "eval_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True).with_variant(String(36), "sqlite"),
        primary_key=True,
        default=uuid.uuid4,
    )
    job_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="queued",
        server_default="queued",
        index=True,
    )
    total_cases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    passed_cases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    metrics_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    error_details: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    results: Mapped[list[EvalResult]] = relationship(
        "EvalResult",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="EvalResult.source_line_number",
    )

    __table_args__ = (
        # Engine-enforced partial unique index: exactly one active run (queued or running)
        Index(
            "idx_single_active_eval_run",
            text("(1)"),
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
    )


class EvalResult(Base):
    """Line-level outcome record for an evaluation dataset input line."""

    __tablename__ = "eval_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True).with_variant(String(36), "sqlite"),
        primary_key=True,
        default=uuid.uuid4,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True).with_variant(String(36), "sqlite"),
        ForeignKey("eval_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_line_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    case_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    ticket_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    validation_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="valid",
        server_default="valid",
    )  # 'valid', 'inconclusive', 'malformed_input', 'model_failure'
    triage_passed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    citation_passed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    safety_passed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    escalation_passed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    execution_details: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    run: Mapped[EvalRun] = relationship(
        "EvalRun",
        back_populates="results",
    )

    __table_args__ = (
        # Preserves every input line independently within a run without row duplication
        UniqueConstraint("run_id", "source_line_number", name="uq_eval_results_run_line"),
        # Enforces that valid cases with non-null case_id cannot be duplicated in the same run
        Index(
            "idx_unique_valid_run_case",
            "run_id",
            "case_id",
            unique=True,
            postgresql_where=text("case_id IS NOT NULL"),
            sqlite_where=text("case_id IS NOT NULL"),
        ),
        Index("idx_eval_results_run_status", "run_id", "validation_status"),
    )

