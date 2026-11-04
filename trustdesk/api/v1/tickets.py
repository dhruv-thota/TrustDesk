from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from trustdesk.core.database import get_db
from trustdesk.core.security import AgentIdentity, verify_demo_token
from trustdesk.schemas.ticket import (
    TicketContextSchema,
    TicketDetailSchema,
    TicketListResponseSchema,
    TicketSummarySchema,
)
from trustdesk.services import ticket_service

router = APIRouter(prefix="/tickets", tags=["Tickets"])


@router.get("", response_model=TicketListResponseSchema)
def list_tickets_endpoint(
    status: str | None = Query(default=None, description="Filter tickets by operational status"),
    customer_id: str | None = Query(default=None, description="Filter tickets by owning customer ID"),
    limit: int = Query(default=50, ge=1, le=100, description="Maximum number of tickets to return"),
    offset: int = Query(default=0, ge=0, description="Offset starting position for pagination"),
    db: Session = Depends(get_db),
    _agent: AgentIdentity = Depends(verify_demo_token),
) -> TicketListResponseSchema:
    """List support tickets with optional status/customer filtering and pagination."""
    items, total = ticket_service.list_tickets(
        db=db,
        status=status,
        customer_id=customer_id,
        limit=limit,
        offset=offset,
    )
    return TicketListResponseSchema(
        items=[TicketSummarySchema.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{ticket_id}", response_model=TicketDetailSchema)
def get_ticket_endpoint(
    ticket_id: str,
    db: Session = Depends(get_db),
    _agent: AgentIdentity = Depends(verify_demo_token),
) -> TicketDetailSchema:
    """Retrieve full details of an individual support ticket."""
    ticket = ticket_service.get_ticket(db=db, ticket_id=ticket_id)
    return TicketDetailSchema.model_validate(ticket)


@router.get("/{ticket_id}/context", response_model=TicketContextSchema)
def get_ticket_context_endpoint(
    ticket_id: str,
    db: Session = Depends(get_db),
    _agent: AgentIdentity = Depends(verify_demo_token),
) -> TicketContextSchema:
    """Retrieve operational context for a ticket including customer, linked order, and past tickets."""
    context = ticket_service.get_ticket_context(db=db, ticket_id=ticket_id)
    return TicketContextSchema.model_validate(context)

