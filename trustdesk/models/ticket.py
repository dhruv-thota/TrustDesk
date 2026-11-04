from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from trustdesk.core.database import Base

if TYPE_CHECKING:
    from trustdesk.models.action import ProposedAction
    from trustdesk.models.ai import DraftResponse, ExecutionTrace, TriageResult
    from trustdesk.models.customer import Customer
    from trustdesk.models.order import Order


class Ticket(Base):
    """Ticket entity representing customer support requests.

    The created_at field serves as the authoritative reference timestamp
    against which all temporal policy windows (returns, warranties) are evaluated.
    """

    __tablename__ = "tickets"

    ticket_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="Original unique dataset ticket identifier")
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.customer_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[str | None] = mapped_column(
        ForeignKey("orders.order_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Authoritative evaluation timestamp for policy checks",
    )
    raw_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        default=dict,
        server_default="{}",
        nullable=False,
        comment="Stores quarantined unresolvable references (e.g. unresolved_order_id)",
    )

    # Relationships
    customer: Mapped[Customer] = relationship("Customer", back_populates="tickets")
    order: Mapped[Order | None] = relationship("Order", back_populates="tickets")
    triage_results: Mapped[list[TriageResult]] = relationship(
        "TriageResult",
        back_populates="ticket",
        cascade="all, delete-orphan",
    )
    draft_responses: Mapped[list[DraftResponse]] = relationship(
        "DraftResponse",
        back_populates="ticket",
        cascade="all, delete-orphan",
    )
    execution_traces: Mapped[list[ExecutionTrace]] = relationship(
        "ExecutionTrace",
        back_populates="ticket",
        cascade="all, delete-orphan",
    )
    proposed_actions: Mapped[list[ProposedAction]] = relationship(
        "ProposedAction",
        back_populates="ticket",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Ticket ticket_id={self.ticket_id!r} customer_id={self.customer_id!r} order_id={self.order_id!r}>"

