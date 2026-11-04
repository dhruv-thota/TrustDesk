from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from trustdesk.core.database import Base

if TYPE_CHECKING:
    from trustdesk.models.knowledge import KBSection
    from trustdesk.models.ticket import Ticket


class TriageResult(Base):
    """Derived AI classification outcome for a support ticket."""

    __tablename__ = "triage_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True).with_variant(String(36), "sqlite"),
        primary_key=True,
        default=uuid.uuid4,
    )
    ticket_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tickets.ticket_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    needs_escalation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    is_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sanitized_diagnostics: Mapped[dict[str, Any]] = mapped_column(
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

    ticket: Mapped[Ticket] = relationship("Ticket", back_populates="triage_results")


class DraftResponse(Base):
    """AI-generated customer response draft grounded in policy evidence."""

    __tablename__ = "draft_responses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True).with_variant(String(36), "sqlite"),
        primary_key=True,
        default=uuid.uuid4,
    )
    ticket_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tickets.ticket_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    draft_text: Mapped[str] = mapped_column(Text, nullable=False)
    has_valid_provenance: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_grounded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    escalation_suggested: Mapped[bool] = mapped_column(Boolean, nullable=False)
    escalation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    ticket: Mapped[Ticket] = relationship("Ticket", back_populates="draft_responses")
    citations: Mapped[list[DraftCitation]] = relationship(
        "DraftCitation",
        back_populates="draft",
        cascade="all, delete-orphan",
    )


class DraftCitation(Base):
    """Individual policy section citation linked to an AI draft response."""

    __tablename__ = "draft_citations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True).with_variant(String(36), "sqlite"),
        primary_key=True,
        default=uuid.uuid4,
    )
    draft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True).with_variant(String(36), "sqlite"),
        ForeignKey("draft_responses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kb_id: Mapped[str] = mapped_column(String(64), nullable=False)
    section_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    quoted_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_valid_provenance: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    draft: Mapped[DraftResponse] = relationship("DraftResponse", back_populates="citations")


class ExecutionTrace(Base):
    """Audit trace for an AI operational execution."""

    __tablename__ = "execution_traces"

    trace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True).with_variant(String(36), "sqlite"),
        primary_key=True,
        default=uuid.uuid4,
    )
    ticket_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tickets.ticket_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_type: Mapped[str] = mapped_column(String(32), nullable=False)
    retrieved_kb_ids: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
        server_default="[]",
    )
    proposed_actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
        server_default="[]",
    )
    executed_actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
        server_default="[]",
    )
    guardrail_outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="passed")
    final_status: Mapped[str] = mapped_column(String(32), nullable=False)
    sanitized_telemetry: Mapped[dict[str, Any]] = mapped_column(
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

    ticket: Mapped[Ticket] = relationship("Ticket", back_populates="execution_traces")
