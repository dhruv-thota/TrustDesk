from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from trustdesk.core.database import Base

if TYPE_CHECKING:
    from trustdesk.models.order import Order
    from trustdesk.models.ticket import Ticket


class Customer(Base):
    """Customer entity representing registered users in the operational database."""

    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="Original unique dataset identifier")
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    orders: Mapped[list[Order]] = relationship("Order", back_populates="customer", cascade="all, delete-orphan")
    tickets: Mapped[list[Ticket]] = relationship("Ticket", back_populates="customer", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Customer customer_id={self.customer_id!r} email={self.email!r}>"

