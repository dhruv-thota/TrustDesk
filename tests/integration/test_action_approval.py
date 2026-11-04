from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from trustdesk.core.config import settings
from trustdesk.core.database import Base, engine, get_db_session
from trustdesk.main import app
from trustdesk.models.action import ActionIdempotency, ProposedAction
from trustdesk.models.ai import ExecutionTrace
from trustdesk.models.customer import Customer
from trustdesk.models.order import Order
from trustdesk.models.ticket import Ticket

client = TestClient(app)
AUTH_HEADER = {"Authorization": f"Bearer {settings.trustdesk_demo_token}"}


@pytest.fixture(autouse=True)
def clean_database():
    """Ensure database schema is clean before each integration test."""
    Base.metadata.create_all(bind=engine)
    with get_db_session() as session:
        session.execute(
            text(
                "TRUNCATE TABLE action_idempotency, proposed_actions, execution_traces, "
                "draft_citations, draft_responses, triage_results, kb_sections, "
                "kb_documents, quarantined_records, tickets, orders, customers CASCADE;"
            )
        )
        session.commit()
    yield


def _seed_ticket(ticket_id: str = "TIK-001", order_id: str | None = "ORD-001") -> dict[str, str]:
    now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    with get_db_session() as session:
        cust = Customer(
            customer_id="CUST-001",
            name="Alice Walker",
            email="alice@example.com",
            metadata_json={"vip": True},
            created_at=now,
        )
        session.add(cust)

        if order_id:
            ord_rec = Order(
                order_id=order_id,
                customer_id="CUST-001",
                order_date=now,
                delivery_date=now,
                status="delivered",
                total_amount=Decimal("120.00"),
                items=[{"sku": "SKU-1", "name": "Wireless Mouse", "price": 120.0}],
            )
            session.add(ord_rec)

        ticket = Ticket(
            ticket_id=ticket_id,
            customer_id="CUST-001",
            order_id=order_id,
            subject="Damaged mouse received",
            message="Item arrived broken. I would like a refund please.",
            status="open",
            created_at=now,
            raw_metadata={},
        )
        session.add(ticket)
        session.commit()

    return {"ticket_id": ticket_id, "order_id": order_id or ""}


# --- EG-P5-01: Action Proposal Creation ---

def test_propose_refund_review_success() -> None:
    """EG-P5-01: Proposing a refund review persists an action in pending_approval status."""
    _seed_ticket("TIK-001", "ORD-001")

    payload = {
        "action_type": "start_refund_review",
        "payload": {"order_id": "ORD-001", "reason": "damaged_goods"},
        "notes": "Customer reported shattered casing.",
    }
    response = client.post(
        "/api/v1/tickets/TIK-001/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json=payload,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["ticket_id"] == "TIK-001"
    assert data["action_type"] == "start_refund_review"
    assert data["status"] == "pending_approval"
    assert data["reviewed_by"] is None
    assert data["action_payload"]["order_id"] == "ORD-001"

    # Verify database persistence
    with get_db_session() as session:
        action = session.scalar(select(ProposedAction).where(ProposedAction.ticket_id == "TIK-001"))
        assert action is not None
        assert action.status == "pending_approval"
        assert action.action_type == "start_refund_review"


def test_propose_refund_review_unauthenticated() -> None:
    """P5-EC-009: Proposal request without authorization header returns 401."""
    _seed_ticket("TIK-001")
    response = client.post(
        "/api/v1/tickets/TIK-001/actions/refund-review/propose",
        json={"action_type": "start_refund_review"},
    )
    assert response.status_code == 401


def test_propose_refund_review_nonexistent_ticket() -> None:
    """P5-EC-010: Proposal against nonexistent ticket ID returns 404."""
    response = client.post(
        "/api/v1/tickets/TIK-NONEXISTENT/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TICKET_NOT_FOUND"


def test_approve_and_reject_nonexistent_action() -> None:
    """P5-EC-011: Approving or rejecting nonexistent action ID returns 404."""
    random_id = uuid.uuid4()
    app_res = client.post(
        f"/api/v1/actions/{random_id}/approve",
        headers={**AUTH_HEADER, "Idempotency-Key": "nonexistent-action-key"},
        json={"notes": "Should 404"},
    )
    assert app_res.status_code == 404
    assert app_res.json()["error"]["code"] == "ACTION_NOT_FOUND"

    rej_res = client.post(
        f"/api/v1/actions/{random_id}/reject",
        headers=AUTH_HEADER,
        json={"reason": "Should 404"},
    )
    assert rej_res.status_code == 404
    assert rej_res.json()["error"]["code"] == "ACTION_NOT_FOUND"


# --- EG-P5-07: Business Uniqueness (U-001) ---

def test_propose_duplicate_active_refund_review_rejected() -> None:
    """EG-P5-07 & P5-EC-006: Second active proposal on same ticket returns 409 Conflict."""
    _seed_ticket("TIK-001", "ORD-001")

    # First proposal
    res1 = client.post(
        "/api/v1/tickets/TIK-001/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review", "payload": {"order_id": "ORD-001"}},
    )
    assert res1.status_code == 201

    # Second proposal on same ticket while first is pending
    res2 = client.post(
        "/api/v1/tickets/TIK-001/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review", "payload": {"order_id": "ORD-001"}},
    )
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "ACTIVE_REVIEW_ALREADY_EXISTS"


# --- EG-P5-02: Authenticated Approval ---

def test_approve_action_success() -> None:
    """EG-P5-02: Human approval executes action, stamps reviewed_by, and records trace."""
    _seed_ticket("TIK-001", "ORD-001")
    prop_res = client.post(
        "/api/v1/tickets/TIK-001/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review", "payload": {"order_id": "ORD-001"}},
    )
    action_id = prop_res.json()["action_id"]

    approve_headers = {**AUTH_HEADER, "Idempotency-Key": "test-key-001"}
    approve_body = {"notes": "Approved damaged mouse refund review"}
    res = client.post(
        f"/api/v1/actions/{action_id}/approve",
        headers=approve_headers,
        json=approve_body,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["action_id"] == action_id
    assert data["status"] == "executed"
    assert data["reviewed_by"] == "demo-agent-001"
    assert data["execution_details"]["status"] == "review_pending"
    assert data["executed_at"] is not None

    # Verify database state
    with get_db_session() as session:
        action = session.scalar(select(ProposedAction).where(ProposedAction.action_id == uuid.UUID(action_id)))
        assert action.status == "executed"
        assert action.reviewed_by == "demo-agent-001"
        assert action.executed_at is not None

        # Verify idempotency record
        idemp = session.scalar(select(ActionIdempotency).where(ActionIdempotency.idempotency_key == "test-key-001"))
        assert idemp.status == "completed"
        assert idemp.response_payload["status"] == "executed"

        # Verify execution trace
        trace = session.scalar(select(ExecutionTrace).where(ExecutionTrace.ticket_id == "TIK-001"))
        assert trace is not None
        assert trace.run_type == "action_execution"
        assert trace.final_status == "success"
        assert len(trace.executed_actions) == 1


# --- EG-P5-04: Idempotent Replay ---

def test_approve_action_idempotent_replay() -> None:
    """EG-P5-04 & P5-EC-001: Same idempotency key and matching payload returns cached 200."""
    _seed_ticket("TIK-001", "ORD-001")
    prop_res = client.post(
        "/api/v1/tickets/TIK-001/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review", "payload": {"order_id": "ORD-001"}},
    )
    action_id = prop_res.json()["action_id"]

    approve_headers = {**AUTH_HEADER, "Idempotency-Key": "replay-key-001"}
    body = {"notes": "Initial approval"}

    # First approval
    res1 = client.post(f"/api/v1/actions/{action_id}/approve", headers=approve_headers, json=body)
    assert res1.status_code == 200
    first_payload = res1.json()

    # Replay approval
    res2 = client.post(f"/api/v1/actions/{action_id}/approve", headers=approve_headers, json=body)
    assert res2.status_code == 200
    assert res2.json() == first_payload

    # Verify no duplicate traces were added
    with get_db_session() as session:
        traces = session.scalars(select(ExecutionTrace).where(ExecutionTrace.ticket_id == "TIK-001")).all()
        assert len(list(traces)) == 1


# --- EG-P5-05 & EG-P5-06: Conflicts and Tampering ---

def test_approve_action_already_processed_with_new_key() -> None:
    """EG-P5-05 & P5-EC-002: Approval attempt on already-executed action with fresh key returns 409."""
    _seed_ticket("TIK-001", "ORD-001")
    prop_res = client.post(
        "/api/v1/tickets/TIK-001/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review"},
    )
    action_id = prop_res.json()["action_id"]

    # First approval succeeds
    client.post(
        f"/api/v1/actions/{action_id}/approve",
        headers={**AUTH_HEADER, "Idempotency-Key": "key-1"},
        json={"notes": "First approval"},
    )

    # Second approval with different key returns 409 Conflict
    res = client.post(
        f"/api/v1/actions/{action_id}/approve",
        headers={**AUTH_HEADER, "Idempotency-Key": "key-2"},
        json={"notes": "Second approval attempt"},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "ACTION_ALREADY_PROCESSED"


def test_approve_action_key_reuse_with_different_payload_conflict() -> None:
    """EG-P5-06 & P5-EC-003: Reusing key with tampered payload returns 409 Conflict."""
    _seed_ticket("TIK-001", "ORD-001")
    prop_res = client.post(
        "/api/v1/tickets/TIK-001/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review"},
    )
    action_id = prop_res.json()["action_id"]

    # Initial call
    client.post(
        f"/api/v1/actions/{action_id}/approve",
        headers={**AUTH_HEADER, "Idempotency-Key": "tamper-key-001"},
        json={"notes": "Original payload", "parameters": {"amount": 50.0}},
    )

    # Tampered call reusing same key
    res = client.post(
        f"/api/v1/actions/{action_id}/approve",
        headers={**AUTH_HEADER, "Idempotency-Key": "tamper-key-001"},
        json={"notes": "Altered payload", "parameters": {"amount": 500.0}},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD"


def test_approve_action_missing_idempotency_key_returns_422() -> None:
    """P5-EC-016: Missing mandatory Idempotency-Key header returns 422."""
    _seed_ticket("TIK-001")
    prop_res = client.post(
        "/api/v1/tickets/TIK-001/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review"},
    )
    action_id = prop_res.json()["action_id"]

    # Call /approve without Idempotency-Key header
    res = client.post(
        f"/api/v1/actions/{action_id}/approve",
        headers=AUTH_HEADER,
        json={"notes": "No key"},
    )
    assert res.status_code == 422


# --- EG-P5-03: Authenticated Rejection ---

def test_reject_action_success() -> None:
    """EG-P5-03: Agent rejection transitions action to rejected and stamps metadata."""
    _seed_ticket("TIK-001", "ORD-001")
    prop_res = client.post(
        "/api/v1/tickets/TIK-001/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review"},
    )
    action_id = prop_res.json()["action_id"]

    res = client.post(
        f"/api/v1/actions/{action_id}/reject",
        headers=AUTH_HEADER,
        json={"reason": "Customer damaged item after delivery", "notes": "Not covered"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "rejected"
    assert data["reviewed_by"] == "demo-agent-001"
    assert data["executed_at"] is None

    # Verify subsequent approval attempt on rejected action returns 409
    app_res = client.post(
        f"/api/v1/actions/{action_id}/approve",
        headers={**AUTH_HEADER, "Idempotency-Key": "after-reject-key"},
        json={"notes": "Try approving"},
    )
    assert app_res.status_code == 409
    assert app_res.json()["error"]["code"] == "ACTION_ALREADY_PROCESSED"


def test_propose_after_rejection_succeeds() -> None:
    """P5-EC-014: Proposing a new action after rejection succeeds with 201."""
    _seed_ticket("TIK-001", "ORD-001")
    prop1 = client.post(
        "/api/v1/tickets/TIK-001/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review"},
    )
    action_id = prop1.json()["action_id"]

    # Reject first action
    client.post(
        f"/api/v1/actions/{action_id}/reject",
        headers=AUTH_HEADER,
        json={"reason": "Missing proof"},
    )

    # Propose second action on same ticket
    prop2 = client.post(
        "/api/v1/tickets/TIK-001/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review", "payload": {"re-opened": True}},
    )
    assert prop2.status_code == 201
    assert prop2.json()["status"] == "pending_approval"


# --- EG-P5-09: Business Failure Audit Commit ---

def test_approve_action_business_failure_commits_failed_state() -> None:
    """EG-P5-09 & P5-EC-004: Business rule failure commits 'failed' status and returns 422."""
    _seed_ticket("TIK-001", "ORD-001")
    prop_res = client.post(
        "/api/v1/tickets/TIK-001/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review"},
    )
    action_id = prop_res.json()["action_id"]

    # Pass simulate_business_failure parameter to trigger business validation error
    res = client.post(
        f"/api/v1/actions/{action_id}/approve",
        headers={**AUTH_HEADER, "Idempotency-Key": "fail-key-001"},
        json={"parameters": {"simulate_business_failure": "order_expired_beyond_threshold"}},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "BUSINESS_RULE_VIOLATION"

    # Verify that status='failed' is COMMITTED in database
    with get_db_session() as session:
        action = session.scalar(select(ProposedAction).where(ProposedAction.action_id == uuid.UUID(action_id)))
        assert action.status == "failed"
        assert "order_expired_beyond_threshold" in action.review_notes

        # Verify idempotency record is marked failed
        idemp = session.scalar(select(ActionIdempotency).where(ActionIdempotency.idempotency_key == "fail-key-001"))
        assert idemp.status == "failed"

        # Verify failed execution trace is persisted
        trace = session.scalar(select(ExecutionTrace).where(ExecutionTrace.ticket_id == "TIK-001"))
        assert trace is not None
        assert trace.final_status == "failed"


def test_approve_attempt_on_failed_action_conflict() -> None:
    """P5-EC-013: Approval on an already failed action returns 409 Conflict."""
    _seed_ticket("TIK-001", "ORD-001")
    prop_res = client.post(
        "/api/v1/tickets/TIK-001/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review"},
    )
    action_id = prop_res.json()["action_id"]

    # Trigger failure
    client.post(
        f"/api/v1/actions/{action_id}/approve",
        headers={**AUTH_HEADER, "Idempotency-Key": "fail-key-002"},
        json={"parameters": {"simulate_business_failure": "validation_error"}},
    )

    # Re-approval attempt with new key returns 409
    res = client.post(
        f"/api/v1/actions/{action_id}/approve",
        headers={**AUTH_HEADER, "Idempotency-Key": "retry-key-002"},
        json={"notes": "Retrying failed action"},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "ACTION_ALREADY_PROCESSED"


def test_propose_after_failure_succeeds() -> None:
    """P5-EC-015: Fresh proposal after confirmed failure succeeds with 201."""
    _seed_ticket("TIK-001", "ORD-001")
    prop1 = client.post(
        "/api/v1/tickets/TIK-001/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review"},
    )
    action_id = prop1.json()["action_id"]

    # Fail execution
    client.post(
        f"/api/v1/actions/{action_id}/approve",
        headers={**AUTH_HEADER, "Idempotency-Key": "fail-key-003"},
        json={"parameters": {"simulate_business_failure": "validation_error"}},
    )

    # Propose new action on same ticket
    prop2 = client.post(
        "/api/v1/tickets/TIK-001/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review", "payload": {"corrected": True}},
    )
    assert prop2.status_code == 201
    assert prop2.json()["status"] == "pending_approval"


# --- EG-P5-10: Transient DB Error Rollback ---

def test_transient_db_error_rolls_back_to_pending_approval() -> None:
    """EG-P5-10 & P5-EC-005: Transient exception rolls back, preserving pending_approval."""
    _seed_ticket("TIK-001", "ORD-001")
    prop_res = client.post(
        "/api/v1/tickets/TIK-001/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review"},
    )
    action_id = prop_res.json()["action_id"]

    # Mock session commit to simulate connection crash / deadlock during execution
    with patch("sqlalchemy.orm.Session.commit", side_effect=RuntimeError("Simulated DB Connection Crash")):
        with pytest.raises(RuntimeError):
            client.post(
                f"/api/v1/actions/{action_id}/approve",
                headers={**AUTH_HEADER, "Idempotency-Key": "transient-key-001"},
                json={"notes": "Approval that crashes DB"},
            )

    # Verify action remains in pending_approval
    with get_db_session() as session:
        action = session.scalar(select(ProposedAction).where(ProposedAction.action_id == uuid.UUID(action_id)))
        assert action.status == "pending_approval"
        assert action.reviewed_by is None
        assert action.executed_at is None


# --- P5-EC-012: Identity Spoofing Protection ---

def test_approver_identity_spoofing_prevented() -> None:
    """P5-EC-012: Custom headers or body fields cannot forge the server-bound agent ID."""
    _seed_ticket("TIK-001", "ORD-001")
    prop_res = client.post(
        "/api/v1/tickets/TIK-001/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review"},
    )
    action_id = prop_res.json()["action_id"]

    spoofed_headers = {
        **AUTH_HEADER,
        "Idempotency-Key": "spoof-key-001",
        "X-Agent-ID": "hacker-agent-999",
    }
    spoofed_body = {
        "notes": "Legitimate note",
        "reviewed_by": "unauthorized-supervisor",
    }
    res = client.post(
        f"/api/v1/actions/{action_id}/approve",
        headers=spoofed_headers,
        json=spoofed_body,
    )
    assert res.status_code == 200
    assert res.json()["reviewed_by"] == "demo-agent-001"

    with get_db_session() as session:
        action = session.scalar(select(ProposedAction).where(ProposedAction.action_id == uuid.UUID(action_id)))
        assert action.reviewed_by == "demo-agent-001"
