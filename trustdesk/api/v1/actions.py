from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, status
from sqlalchemy.orm import Session

from trustdesk.core.database import get_db
from trustdesk.core.logging import get_logger
from trustdesk.core.security import AgentIdentity, verify_demo_token
from trustdesk.schemas.action import (
    ActionApproveRequestSchema,
    ActionExecutionResultSchema,
    ActionProposalCreateSchema,
    ActionRejectRequestSchema,
    ProposedActionSchema,
)
from trustdesk.services.action_service import (
    approve_action,
    list_ticket_actions,
    propose_refund_review,
    reject_action,
)

logger = get_logger(__name__)

router = APIRouter(tags=["Controlled Actions"])


@router.get(
    "/tickets/{ticket_id}/actions",
    response_model=list[ProposedActionSchema],
    status_code=status.HTTP_200_OK,
)
def list_ticket_actions_endpoint(
    ticket_id: str,
    db: Session = Depends(get_db),
    _agent: AgentIdentity = Depends(verify_demo_token),
) -> Any:
    """Retrieve all proposed operational actions for a ticket ordered newest first (U-014)."""
    return list_ticket_actions(db=db, ticket_id=ticket_id)



@router.post(
    "/tickets/{ticket_id}/actions/refund-review/propose",
    response_model=ProposedActionSchema,
    status_code=status.HTTP_201_CREATED,
)
def propose_refund_review_endpoint(
    ticket_id: str,
    proposal: ActionProposalCreateSchema = Body(default_factory=ActionProposalCreateSchema),
    db: Session = Depends(get_db),
    agent: AgentIdentity = Depends(verify_demo_token),
) -> Any:
    """Record a human or AI recommendation to start an internal refund review.

    Persists the action in pending_approval status. Enforces U-001 partial unique constraint.
    """
    return propose_refund_review(
        db=db,
        ticket_id=ticket_id,
        proposal=proposal,
        proposed_by=agent.role or "agent",
    )


@router.post(
    "/actions/{action_id}/approve",
    response_model=ActionExecutionResultSchema,
    status_code=status.HTTP_200_OK,
)
def approve_action_endpoint(
    action_id: uuid.UUID,
    payload: ActionApproveRequestSchema = Body(default_factory=ActionApproveRequestSchema),
    idempotency_key: str = Header(..., alias="Idempotency-Key", description="Mandatory unique request idempotency key"),
    db: Session = Depends(get_db),
    agent: AgentIdentity = Depends(verify_demo_token),
) -> Any:
    """Authenticated human approval of a pending operational action.

    Enforces row locking, idempotent replay, failure audit commit, and server identity binding.
    """
    result, _status_code = approve_action(
        db=db,
        action_id=action_id,
        idempotency_key=idempotency_key,
        request_payload=payload,
        agent=agent,
    )
    return result


@router.post(
    "/actions/{action_id}/reject",
    response_model=ProposedActionSchema,
    status_code=status.HTTP_200_OK,
)
def reject_action_endpoint(
    action_id: uuid.UUID,
    payload: ActionRejectRequestSchema = Body(default_factory=ActionRejectRequestSchema),
    db: Session = Depends(get_db),
    agent: AgentIdentity = Depends(verify_demo_token),
) -> Any:
    """Authenticated human rejection of a pending operational action.

    Transitions action to terminal 'rejected' status.
    """
    return reject_action(
        db=db,
        action_id=action_id,
        request_payload=payload,
        agent=agent,
    )

