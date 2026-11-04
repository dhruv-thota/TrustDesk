from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from trustdesk.schemas.ticket import (
    CustomerProfileSchema,
    OrderDetailSchema,
    TicketContextSchema,
    TicketDetailSchema,
    TicketListResponseSchema,
    TicketSummarySchema,
)


def test_ticket_summary_schema_valid() -> None:
    """Verifies that TicketSummarySchema validates properly formatted ticket data (P2-EV-005)."""
    now = datetime.now(timezone.utc)
    data = {
        "ticket_id": "TIK-001",
        "customer_id": "CUST-001",
        "order_id": "ORD-001",
        "subject": "Damaged Package Received",
        "status": "open",
        "created_at": now,
        "raw_metadata": {"channel": "email"},
    }
    schema = TicketSummarySchema.model_validate(data)
    assert schema.ticket_id == "TIK-001"
    assert schema.order_id == "ORD-001"
    assert schema.status == "open"
    assert schema.raw_metadata["channel"] == "email"


def test_ticket_summary_schema_null_order() -> None:
    """Verifies TicketSummarySchema allows order_id to be None (P2-EC-002)."""
    data = {
        "ticket_id": "TIK-002",
        "customer_id": "CUST-001",
        "order_id": None,
        "subject": "General Inquiries",
        "status": "open",
        "created_at": datetime.now(timezone.utc),
    }
    schema = TicketSummarySchema.model_validate(data)
    assert schema.order_id is None
    assert schema.raw_metadata == {}


def test_ticket_detail_schema_missing_required_fields() -> None:
    """Verifies that missing required fields like message raise ValidationError (P2-EV-005)."""
    data = {
        "ticket_id": "TIK-003",
        "customer_id": "CUST-001",
        "subject": "Missing message field",
        "status": "open",
        "created_at": datetime.now(timezone.utc),
    }
    with pytest.raises(ValidationError):
        TicketDetailSchema.model_validate(data)


def test_ticket_context_schema_with_order_and_past_tickets() -> None:
    """Verifies full TicketContextSchema validation with linked order and history (P2-EV-005)."""
    now = datetime.now(timezone.utc)
    data = {
        "ticket": {
            "ticket_id": "TIK-100",
            "customer_id": "CUST-100",
            "order_id": "ORD-100",
            "subject": "Return Request",
            "message": "I would like to return this jacket.",
            "status": "open",
            "created_at": now,
            "raw_metadata": {},
        },
        "customer": {
            "customer_id": "CUST-100",
            "name": "Jane Doe",
            "email": "jane@example.com",
            "metadata_json": {"tier": "gold"},
            "created_at": now,
        },
        "order": {
            "order_id": "ORD-100",
            "customer_id": "CUST-100",
            "order_date": now,
            "delivery_date": now,
            "status": "delivered",
            "total_amount": Decimal("129.99"),
            "items": [{"sku": "JKT-01", "name": "Winter Jacket", "price": 129.99, "qty": 1}],
        },
        "past_tickets": [
            {
                "ticket_id": "TIK-099",
                "customer_id": "CUST-100",
                "order_id": "ORD-050",
                "subject": "Prior Shipping Question",
                "status": "closed",
                "created_at": now,
                "raw_metadata": {},
            }
        ],
    }
    context = TicketContextSchema.model_validate(data)
    assert context.ticket.ticket_id == "TIK-100"
    assert context.customer.name == "Jane Doe"
    assert context.customer.metadata == {"tier": "gold"}
    assert context.order is not None
    assert context.order.order_id == "ORD-100"
    assert len(context.past_tickets) == 1
    assert context.past_tickets[0].ticket_id == "TIK-099"


def test_ticket_context_schema_unlinked_order_is_none() -> None:
    """Verifies TicketContextSchema gracefully handles order = None (P2-EC-002)."""
    now = datetime.now(timezone.utc)
    data = {
        "ticket": {
            "ticket_id": "TIK-101",
            "customer_id": "CUST-101",
            "order_id": None,
            "subject": "Pre-sales question",
            "message": "Do you ship internationally?",
            "status": "open",
            "created_at": now,
            "raw_metadata": {"unresolved_order_id": None},
        },
        "customer": {
            "customer_id": "CUST-101",
            "name": "Bob Smith",
            "email": "bob@example.com",
            "created_at": now,
        },
        "order": None,
        "past_tickets": [],
    }
    context = TicketContextSchema.model_validate(data)
    assert context.ticket.order_id is None
    assert context.order is None
    assert context.past_tickets == []


def test_ticket_list_response_schema() -> None:
    """Verifies TicketListResponseSchema envelope structure (P2-EV-006)."""
    now = datetime.now(timezone.utc)
    data = {
        "items": [
            {
                "ticket_id": "TIK-1",
                "customer_id": "CUST-1",
                "subject": "Issue 1",
                "status": "open",
                "created_at": now,
            }
        ],
        "total": 1,
        "limit": 50,
        "offset": 0,
    }
    res = TicketListResponseSchema.model_validate(data)
    assert res.total == 1
    assert len(res.items) == 1
    assert res.items[0].ticket_id == "TIK-1"

