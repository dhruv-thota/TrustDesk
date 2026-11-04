from __future__ import annotations

import uuid
import pytest
from pydantic import ValidationError

from trustdesk.schemas.action import (
    ActionApproveRequestSchema,
    ActionExecutionResultSchema,
    ActionProposalCreateSchema,
    ActionRejectRequestSchema,
    ProposedActionSchema,
)
from trustdesk.services.action_service import compute_request_hash


def test_action_proposal_schema_valid() -> None:
    """Verifies that start_refund_review proposal schema parses cleanly."""
    proposal = ActionProposalCreateSchema(
        action_type="start_refund_review",
        payload={"order_id": "ORD-123", "reason": "damaged"},
        notes="Agent verified receipt",
    )
    assert proposal.action_type == "start_refund_review"
    assert proposal.payload["order_id"] == "ORD-123"
    assert proposal.notes == "Agent verified receipt"


def test_action_proposal_schema_rejects_unsupported_action() -> None:
    """Verifies that operational actions outside start_refund_review trigger ValidationError."""
    with pytest.raises(ValidationError):
        ActionProposalCreateSchema(
            action_type="create_replacement_order",  # type: ignore[arg-type]
            payload={"order_id": "ORD-123"},
        )


def test_compute_request_hash_canonicalization() -> None:
    """Verifies canonical JSON hashing is invariant to dict key ordering."""
    action_id = uuid.uuid4()
    payload_a = {"reason": "damaged", "order_id": "ORD-001", "amount": 50.0}
    payload_b = {"amount": 50.0, "order_id": "ORD-001", "reason": "damaged"}

    hash_a = compute_request_hash(action_id, payload_a)
    hash_b = compute_request_hash(action_id, payload_b)
    assert hash_a == hash_b

    # Different action ID must yield different hash
    other_id = uuid.uuid4()
    hash_other = compute_request_hash(other_id, payload_a)
    assert hash_a != hash_other

    # Altered payload must yield different hash
    payload_altered = {"reason": "damaged", "order_id": "ORD-002", "amount": 50.0}
    hash_altered = compute_request_hash(action_id, payload_altered)
    assert hash_a != hash_altered


def test_action_execution_result_schema() -> None:
    """Verifies ActionExecutionResultSchema parsing and serializing."""
    action_id = uuid.uuid4()
    now_dt = "2026-11-04T12:00:00Z"
    result = ActionExecutionResultSchema.model_validate({
        "action_id": str(action_id),
        "ticket_id": "TIK-001",
        "action_type": "start_refund_review",
        "status": "executed",
        "reviewed_by": "demo-agent-001",
        "reviewed_at": now_dt,
        "executed_at": now_dt,
        "execution_details": {"registration_id": "REF-REV-001"},
    })
    assert result.status == "executed"
    assert result.reviewed_by == "demo-agent-001"
    assert result.execution_details["registration_id"] == "REF-REV-001"

