from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from trustdesk.core.exceptions import (
    ActionAlreadyProcessedError,
    ActionNotFoundError,
    ActiveReviewExistsError,
    BusinessRuleViolationError,
    IdempotencyConflictError,
    TicketNotFoundError,
    UnsupportedActionError,
)
from trustdesk.core.logging import get_logger
from trustdesk.core.security import AgentIdentity
from trustdesk.models.action import ActionIdempotency, ProposedAction
from trustdesk.models.ai import ExecutionTrace
from trustdesk.models.ticket import Ticket
from trustdesk.schemas.action import (
    ActionApproveRequestSchema,
    ActionExecutionResultSchema,
    ActionProposalCreateSchema,
    ActionRejectRequestSchema,
)
from trustdesk.tools.catalog import ALLOWED_OPERATIONAL_ACTIONS

logger = get_logger(__name__)


def compute_request_hash(action_id: uuid.UUID | str, payload: dict[str, Any] | None) -> str:
    """Computes deterministic SHA256 hash of action ID and canonical JSON request parameters."""
    json_canonical = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"))
    raw_key = f"{str(action_id)}:{json_canonical}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def propose_refund_review(
    db: Session,
    ticket_id: str,
    proposal: ActionProposalCreateSchema,
    proposed_by: str = "agent",
) -> ProposedAction:
    """Proposes a new refund review action for a ticket in pending_approval status.

    Enforces U-001 partial unique constraint: at most one pending or executed review per ticket.
    """
    if proposal.action_type not in ALLOWED_OPERATIONAL_ACTIONS:
        raise UnsupportedActionError(action_type=proposal.action_type)

    # 1. Verify ticket existence
    ticket = db.scalar(select(Ticket).where(Ticket.ticket_id == ticket_id))
    if not ticket:
        raise TicketNotFoundError(ticket_id=ticket_id)

    # 2. Check for active review on ticket (Application-level pre-check)
    existing_stmt = select(ProposedAction).where(
        ProposedAction.ticket_id == ticket_id,
        ProposedAction.action_type == proposal.action_type,
        ProposedAction.status.in_(["pending_approval", "executed"]),
    )
    if db.scalar(existing_stmt):
        raise ActiveReviewExistsError(ticket_id=ticket_id)

    # 3. Create proposed action record
    action = ProposedAction(
        ticket_id=ticket_id,
        action_type=proposal.action_type,
        status="pending_approval",
        action_payload=proposal.payload,
        proposed_by=proposed_by,
        review_notes=proposal.notes,
    )
    db.add(action)

    try:
        db.commit()
        db.refresh(action)
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Uniqueness violation proposing refund review for ticket %s: %s", ticket_id, exc)
        raise ActiveReviewExistsError(ticket_id=ticket_id) from exc

    logger.info("Created refund review proposal %s for ticket %s", action.action_id, ticket_id)
    return action


def approve_action(
    db: Session,
    action_id: uuid.UUID,
    idempotency_key: str,
    request_payload: ActionApproveRequestSchema,
    agent: AgentIdentity,
) -> tuple[dict[str, Any], int]:
    """Atomically executes human approval of a pending operational action with strict idempotency."""
    incoming_hash = compute_request_hash(action_id, request_payload.model_dump())

    # 1. Replay Ordering: Check completed idempotency record BEFORE evaluating terminal status
    existing_idemp = db.scalar(
        select(ActionIdempotency).where(ActionIdempotency.idempotency_key == idempotency_key)
    )
    if existing_idemp:
        # Verify key is bound to the exact same action_id and payload
        if str(existing_idemp.action_id) != str(action_id) or existing_idemp.request_hash != incoming_hash:
            raise IdempotencyConflictError(
                key=idempotency_key,
                error_code="IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD",
                message=f"Idempotency key '{idempotency_key}' reuse with modified payload or different action ID.",
                details={"action_id": str(action_id), "stored_action_id": str(existing_idemp.action_id)},
            )

        if existing_idemp.status == "completed":
            logger.info("Returning cached execution response for idempotency key %s", idempotency_key)
            return existing_idemp.response_payload or {}, 200

        if existing_idemp.status == "in_progress":
            raise IdempotencyConflictError(
                key=idempotency_key,
                error_code="CONCURRENT_REQUEST_IN_PROGRESS",
                message=f"A request with idempotency key '{idempotency_key}' is currently in progress.",
            )

        if existing_idemp.status == "failed":
            raise IdempotencyConflictError(
                key=idempotency_key,
                error_code="IDEMPOTENCY_KEY_PREVIOUSLY_FAILED",
                message=f"Idempotency key '{idempotency_key}' was used in a previously failed execution attempt.",
            )

    # 2. Acquire row lock on proposed_actions
    action_stmt = (
        select(ProposedAction)
        .where(ProposedAction.action_id == action_id)
        .with_for_update()
    )
    action = db.scalar(action_stmt)
    if not action:
        raise ActionNotFoundError(action_id=str(action_id))

    # 3. Check current status under lock
    if action.status != "pending_approval":
        raise ActionAlreadyProcessedError(
            action_id=str(action_id),
            current_status=action.status,
        )

    # 4. Insert in-progress idempotency tracking
    idemp_record = ActionIdempotency(
        idempotency_key=idempotency_key,
        action_id=action_id,
        request_hash=incoming_hash,
        status="in_progress",
    )
    db.add(idemp_record)
    db.flush()

    # 5. Business rule validation
    # Check for simulated or confirmed business failures (P5-EC-004, U-008)
    simulated_failure = (
        action.action_payload.get("simulate_business_failure")
        or request_payload.parameters.get("simulate_business_failure")
    )
    if simulated_failure:
        failure_reason = str(simulated_failure)
        action.status = "failed"
        action.reviewed_by = agent.agent_id
        action.review_notes = f"Execution failed: {failure_reason}"
        action.reviewed_at = datetime.now(timezone.utc)
        idemp_record.status = "failed"
        idemp_record.completed_at = datetime.now(timezone.utc)

        # Audit failure trace
        trace = ExecutionTrace(
            ticket_id=action.ticket_id,
            run_type="action_execution",
            retrieved_kb_ids=[],
            proposed_actions=[{
                "action_id": str(action.action_id),
                "action_type": action.action_type,
                "payload": action.action_payload,
            }],
            executed_actions=[],
            guardrail_outcome="business_rule_violation",
            final_status="failed",
            sanitized_telemetry={"reviewed_by": agent.agent_id, "error": failure_reason},
        )
        db.add(trace)
        db.commit()

        raise BusinessRuleViolationError(
            message=f"Action execution failed: {failure_reason}",
            details={"action_id": str(action.action_id), "status": "failed"},
        )

    # 6. Execute successful approval
    now = datetime.now(timezone.utc)
    action.status = "executed"
    action.reviewed_by = agent.agent_id
    action.review_notes = request_payload.notes
    action.reviewed_at = now
    action.executed_at = now

    result_payload = {
        "action_id": str(action.action_id),
        "ticket_id": action.ticket_id,
        "action_type": action.action_type,
        "status": "executed",
        "reviewed_by": agent.agent_id,
        "reviewed_at": now.isoformat(),
        "executed_at": now.isoformat(),
        "execution_details": {
            "registration_id": f"REF-REV-{str(action.action_id)[:8].upper()}",
            "review_queue": "human_refund_investigation",
            "order_id": action.action_payload.get("order_id"),
            "status": "review_pending",
        },
        "error_details": None,
    }

    idemp_record.status = "completed"
    idemp_record.response_payload = result_payload
    idemp_record.completed_at = now

    trace = ExecutionTrace(
        ticket_id=action.ticket_id,
        run_type="action_execution",
        retrieved_kb_ids=[],
        proposed_actions=[{
            "action_id": str(action.action_id),
            "action_type": action.action_type,
            "payload": action.action_payload,
        }],
        executed_actions=[{
            "action_type": action.action_type,
            "action_id": str(action.action_id),
            "payload": action.action_payload,
            "reviewed_by": agent.agent_id,
            "executed_at": now.isoformat(),
        }],
        guardrail_outcome="passed",
        final_status="success",
        sanitized_telemetry={"reviewed_by": agent.agent_id, "latency_ms": 10},
    )
    db.add(trace)
    db.commit()

    logger.info("Successfully executed refund review action %s for ticket %s", action_id, action.ticket_id)
    return result_payload, 200


def reject_action(
    db: Session,
    action_id: uuid.UUID,
    request_payload: ActionRejectRequestSchema,
    agent: AgentIdentity,
) -> ProposedAction:
    """Atomically rejects a pending operational action with row-level locking."""
    action_stmt = (
        select(ProposedAction)
        .where(ProposedAction.action_id == action_id)
        .with_for_update()
    )
    action = db.scalar(action_stmt)
    if not action:
        raise ActionNotFoundError(action_id=str(action_id))

    if action.status != "pending_approval":
        raise ActionAlreadyProcessedError(
            action_id=str(action_id),
            current_status=action.status,
        )

    now = datetime.now(timezone.utc)
    action.status = "rejected"
    action.reviewed_by = agent.agent_id
    action.review_notes = request_payload.notes or request_payload.reason
    action.reviewed_at = now
    action.executed_at = None

    trace = ExecutionTrace(
        ticket_id=action.ticket_id,
        run_type="action_rejection",
        retrieved_kb_ids=[],
        proposed_actions=[{
            "action_id": str(action.action_id),
            "action_type": action.action_type,
            "payload": action.action_payload,
        }],
        executed_actions=[],
        guardrail_outcome="rejected_by_human",
        final_status="rejected",
        sanitized_telemetry={"reviewed_by": agent.agent_id, "rejection_reason": request_payload.reason},
    )
    db.add(trace)
    db.commit()
    db.refresh(action)

    logger.info("Action %s rejected by agent %s", action_id, agent.agent_id)
    return action


def list_ticket_actions(db: Session, ticket_id: str) -> list[ProposedAction]:
    """Retrieve all proposed actions for a ticket ordered newest first (U-014).

    Raises TicketNotFoundError if the ticket does not exist.
    """
    ticket = db.scalar(select(Ticket).where(Ticket.ticket_id == ticket_id))
    if not ticket:
        raise TicketNotFoundError(ticket_id=ticket_id)

    stmt = (
        select(ProposedAction)
        .where(ProposedAction.ticket_id == ticket_id)
        .order_by(ProposedAction.created_at.desc())
    )
    return list(db.scalars(stmt).all())


