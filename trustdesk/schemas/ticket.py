from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CustomerProfileSchema(BaseModel):
    """Customer profile information attached to ticket context."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    customer_id: str
    name: str | None = None
    email: str | None = None
    metadata: dict[str, Any] | None = Field(
        default=None,
        validation_alias="metadata_json",
        serialization_alias="metadata",
    )
    created_at: datetime


class OrderItemSchema(BaseModel):
    """Item record within an order."""

    model_config = ConfigDict(extra="allow")

    sku: str | None = None
    name: str | None = None
    price: Decimal | float | None = None
    qty: int | None = None


class OrderDetailSchema(BaseModel):
    """Order detail information linked to a support ticket."""

    model_config = ConfigDict(from_attributes=True)

    order_id: str
    customer_id: str
    order_date: datetime
    delivery_date: datetime | None = None
    status: str | None = None
    total_amount: Decimal | float | None = None
    items: list[dict[str, Any]] | None = None


class TicketSummarySchema(BaseModel):
    """Concise ticket overview representation for list views."""

    model_config = ConfigDict(from_attributes=True)

    ticket_id: str
    customer_id: str
    order_id: str | None = None
    subject: str
    status: str
    created_at: datetime
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class TicketDetailSchema(BaseModel):
    """Complete ticket detail representation."""

    model_config = ConfigDict(from_attributes=True)

    ticket_id: str
    customer_id: str
    order_id: str | None = None
    subject: str
    message: str
    status: str
    created_at: datetime
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class TicketListResponseSchema(BaseModel):
    """Paginated collection response for tickets."""

    items: list[TicketSummarySchema]
    total: int
    limit: int
    offset: int


class TicketContextSchema(BaseModel):
    """Assembled operational context for a support ticket."""

    ticket: TicketDetailSchema
    customer: CustomerProfileSchema
    order: OrderDetailSchema | None = None
    past_tickets: list[TicketSummarySchema] = Field(default_factory=list)
