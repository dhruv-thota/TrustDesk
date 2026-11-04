from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from trustdesk.core.exceptions import TicketNotFoundError
from trustdesk.core.logging import get_logger
from trustdesk.models.customer import Customer
from trustdesk.models.order import Order
from trustdesk.models.ticket import Ticket

logger = get_logger(__name__)


def list_tickets(
    db: Session,
    status: str | None = None,
    customer_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Ticket], int]:
    """Retrieve paginated tickets with optional filtering by status and customer ID.

    Returns a tuple of (items, total_count).
    """
    base_query = select(Ticket)

    if status:
        base_query = base_query.where(Ticket.status == status)
    if customer_id:
        base_query = base_query.where(Ticket.customer_id == customer_id)

    # Count total matching records
    count_stmt = select(func.count()).select_from(base_query.subquery())
    total = db.scalar(count_stmt) or 0

    # Retrieve slice ordered by created_at descending
    items_stmt = (
        base_query.order_by(Ticket.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = list(db.scalars(items_stmt).all())

    return items, total


def get_ticket(db: Session, ticket_id: str) -> Ticket:
    """Retrieve an individual ticket by ID, raising TicketNotFoundError if not found."""
    stmt = select(Ticket).where(Ticket.ticket_id == ticket_id)
    ticket = db.scalar(stmt)
    if not ticket:
        raise TicketNotFoundError(ticket_id=ticket_id)
    return ticket


def get_ticket_context(db: Session, ticket_id: str) -> dict[str, Any]:
    """Assemble complete operational context for a ticket.

    Retrieves the ticket, its owning customer profile, linked order (or None if unlinked),
    and other past tickets for that customer (excluding the active ticket).
    """
    stmt = (
        select(Ticket)
        .options(
            joinedload(Ticket.customer),
            joinedload(Ticket.order),
        )
        .where(Ticket.ticket_id == ticket_id)
    )
    ticket = db.scalar(stmt)
    if not ticket:
        raise TicketNotFoundError(ticket_id=ticket_id)

    customer = ticket.customer
    order = ticket.order if ticket.order_id else None

    # Fetch customer's other tickets excluding active ticket
    past_tickets_stmt = (
        select(Ticket)
        .where(Ticket.customer_id == ticket.customer_id)
        .where(Ticket.ticket_id != ticket.ticket_id)
        .order_by(Ticket.created_at.desc())
    )
    past_tickets = list(db.scalars(past_tickets_stmt).all())

    return {
        "ticket": ticket,
        "customer": customer,
        "order": order,
        "past_tickets": past_tickets,
    }

