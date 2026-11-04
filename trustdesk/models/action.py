from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from trustdesk.core.database import Base

if TYPE_CHECKING:
    from trustdesk.models.ticket import Ticket


class ProposedAction(Base):
    """Operational action recommendation awaiting or having completed human review."""

    __tablename__ = "proposed_actions"

    action_id: Mapped[uuid.UUID] = mapped_column(
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
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, default="start_refund_review")
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending_approval",
        server_default="pending_approval",
    )
    action_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    proposed_by: Mapped[str] = mapped_column(String(32), nullable=False, default="ai")
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    ticket: Mapped[Ticket] = relationship("Ticket", back_populates="proposed_actions")
    idempotency_records: Mapped[list[ActionIdempotency]] = relationship(
        "ActionIdempotency",
        back_populates="action",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "idx_unique_active_refund_review",
            "ticket_id",
            "action_type",
            unique=True,
            postgresql_where=text("status IN ('pending_approval', 'executed')"),
            sqlite_where=text("status IN ('pending_approval', 'executed')"),
        ),
    )


class ActionIdempotency(Base):
    """Persistent request idempotency tracking for sensitive operational actions."""

    __tablename__ = "action_idempotency"

    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    action_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True).with_variant(String(36), "sqlite"),
        ForeignKey("proposed_actions.action_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # 'in_progress', 'completed', 'failed'
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    action: Mapped[ProposedAction] = relationship("ProposedAction", back_populates="idempotency_records")

