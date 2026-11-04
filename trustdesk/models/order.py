from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from trustdesk.core.database import Base

if TYPE_CHECKING:
    from trustdesk.models.customer import Customer
    from trustdesk.models.ticket import Ticket


class Order(Base):
    """Order entity representing purchases placed by customers."""

    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="Original unique dataset order identifier")
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.customer_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivery_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    items: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
        default=list,
    )

    # Relationships
    customer: Mapped[Customer] = relationship("Customer", back_populates="orders")
    tickets: Mapped[list[Ticket]] = relationship("Ticket", back_populates="order")

    def __repr__(self) -> str:
        return f"<Order order_id={self.order_id!r} customer_id={self.customer_id!r} total={self.total_amount!r}>"

