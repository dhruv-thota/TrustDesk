from __future__ import annotations

import concurrent.futures
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from trustdesk.core.config import settings
from trustdesk.core.database import Base, engine, get_db_session
from trustdesk.main import app
from trustdesk.models.action import ProposedAction
from trustdesk.models.ai import ExecutionTrace
from trustdesk.models.customer import Customer
from trustdesk.models.order import Order
from trustdesk.models.ticket import Ticket

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


def _seed_ticket(ticket_id: str = "TIK-CONC-001") -> str:
    now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    with get_db_session() as session:
        cust = Customer(
            customer_id="CUST-CONC-001",
            name="Bob Concurrency",
            email="bob@example.com",
            created_at=now,
        )
        session.add(cust)
        ord_rec = Order(
            order_id="ORD-CONC-001",
            customer_id="CUST-CONC-001",
            order_date=now,
            delivery_date=now,
            status="delivered",
            total_amount=Decimal("200.00"),
        )
        session.add(ord_rec)
        ticket = Ticket(
            ticket_id=ticket_id,
            customer_id="CUST-CONC-001",
            order_id="ORD-CONC-001",
            subject="Concurrency check ticket",
            message="Item damaged on delivery.",
            status="open",
            created_at=now,
        )
        session.add(ticket)
        session.commit()
    return ticket_id


def test_concurrent_double_approval_same_idempotency_key() -> None:
    """EG-P5-08: Simultaneous approvals with identical idempotency key serialize safely."""
    ticket_id = _seed_ticket("TIK-CONC-001")
    client = TestClient(app)

    prop = client.post(
        f"/api/v1/tickets/{ticket_id}/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review", "payload": {"order_id": "ORD-CONC-001"}},
    )
    action_id = prop.json()["action_id"]

    idemp_key = f"conc-key-{uuid.uuid4()}"
    headers = {**AUTH_HEADER, "Idempotency-Key": idemp_key}
    body = {"notes": "Concurrent double-click approval"}

    def send_approval():
        c = TestClient(app)
        return c.post(f"/api/v1/actions/{action_id}/approve", headers=headers, json=body)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(send_approval)
        f2 = executor.submit(send_approval)
        res1 = f1.result()
        res2 = f2.result()

    # Both requests must return HTTP 200 (one executed, one idempotent replay)
    # or one returns 200 and one handles concurrent in-progress (409)
    assert 200 in [res1.status_code, res2.status_code]
    for r in [res1, res2]:
        assert r.status_code in [200, 409]

    # Verify exactly one execution trace was recorded in the database
    with get_db_session() as session:
        action = session.scalar(select(ProposedAction).where(ProposedAction.action_id == uuid.UUID(action_id)))
        assert action.status == "executed"
        traces = session.scalars(
            select(ExecutionTrace).where(ExecutionTrace.ticket_id == ticket_id)
        ).all()
        assert len(list(traces)) == 1


def test_concurrent_approval_different_idempotency_keys() -> None:
    """EG-P5-08: Simultaneous approvals with different keys result in exactly one execution."""
    ticket_id = _seed_ticket("TIK-CONC-002")
    client = TestClient(app)

    prop = client.post(
        f"/api/v1/tickets/{ticket_id}/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review", "payload": {"order_id": "ORD-CONC-001"}},
    )
    action_id = prop.json()["action_id"]

    def send_approval(key: str):
        c = TestClient(app)
        return c.post(
            f"/api/v1/actions/{action_id}/approve",
            headers={**AUTH_HEADER, "Idempotency-Key": key},
            json={"notes": f"Approval with {key}"},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(send_approval, f"key-a-{uuid.uuid4()}")
        f2 = executor.submit(send_approval, f"key-b-{uuid.uuid4()}")
        res1 = f1.result()
        res2 = f2.result()

    status_codes = sorted([res1.status_code, res2.status_code])
    assert status_codes == [200, 409]

    # Verify database has single execution record
    with get_db_session() as session:
        action = session.scalar(select(ProposedAction).where(ProposedAction.action_id == uuid.UUID(action_id)))
        assert action.status == "executed"
        traces = session.scalars(
            select(ExecutionTrace).where(ExecutionTrace.ticket_id == ticket_id)
        ).all()
        assert len(list(traces)) == 1


def test_concurrent_proposals_on_same_ticket() -> None:
    """EG-P5-07 & U-001: Concurrent proposals for same ticket result in exactly one active proposal."""
    ticket_id = _seed_ticket("TIK-CONC-003")

    def send_proposal(idx: int):
        c = TestClient(app)
        return c.post(
            f"/api/v1/tickets/{ticket_id}/actions/refund-review/propose",
            headers=AUTH_HEADER,
            json={"action_type": "start_refund_review", "payload": {"index": idx}},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(send_proposal, 1)
        f2 = executor.submit(send_proposal, 2)
        res1 = f1.result()
        res2 = f2.result()

    status_codes = sorted([res1.status_code, res2.status_code])
    assert status_codes == [201, 409]

    with get_db_session() as session:
        actions = session.scalars(
            select(ProposedAction).where(ProposedAction.ticket_id == ticket_id)
        ).all()
        assert len(list(actions)) == 1

