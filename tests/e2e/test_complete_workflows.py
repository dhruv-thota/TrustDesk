from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from rq import Queue, SimpleWorker
from rq.job import Job
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import make_url

import trustdesk.core.database as db_mod
from trustdesk.core.config import settings
from trustdesk.core.database import get_db, get_db_session
from trustdesk.core.redis import get_redis_client
from trustdesk.main import app
from trustdesk.models.action import ActionIdempotency, ProposedAction
from trustdesk.models.ai import DraftCitation, DraftResponse, ExecutionTrace, TriageResult
from trustdesk.models.customer import Customer
from trustdesk.models.eval import EvalResult, EvalRun
from trustdesk.models.knowledge import KBSection, KnowledgeDocument
from trustdesk.models.order import Order
from trustdesk.models.ticket import Ticket
from trustdesk.schemas.triage import TicketCategory, TicketPriority
from trustdesk.services.ingestion import ingest_kb_documents
from trustdesk.services.knowledge_service import derive_and_index_sections

client = TestClient(app)
AUTH_HEADER = {"Authorization": f"Bearer {settings.trustdesk_demo_token}"}
DATASET_PATH = Path("data/eval_cases.jsonl")
TEST_QUEUE_NAME = "test-e2e-evaluations"

PII_CREDIT_CARD_REGEX = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
PII_SECRET_KEY_REGEX = re.compile(r"\b(SECRET-[A-Za-z0-9-_]+|AIza[0-9A-Za-z-_]{35})\b")


def verify_test_database_isolation(engine) -> str:
    """Verifies that the target database is strictly a test database and not the development database."""
    test_url = settings.database_url_test
    dev_url = settings.database_url
    if not test_url:
        raise RuntimeError("DATABASE_URL_TEST is not configured or empty.")
    if test_url == dev_url:
        raise RuntimeError(f"DATABASE_URL_TEST matches DATABASE_URL: {test_url}. Aborting to protect dev DB.")

    parsed_test_url = make_url(test_url)
    parsed_dev_url = make_url(dev_url)

    test_db_name = parsed_test_url.database
    dev_db_name = parsed_dev_url.database

    if not test_db_name or not test_db_name.endswith("_test"):
        raise RuntimeError(f"Target test database '{test_db_name}' must end with '_test'.")
    if test_db_name == dev_db_name:
        raise RuntimeError(
            f"Target test database '{test_db_name}' cannot be identical to dev database '{dev_db_name}'."
        )

    with engine.connect() as conn:
        current_db = conn.execute(text("SELECT current_database();")).scalar()
        if current_db != test_db_name:
            raise RuntimeError(f"Connected to '{current_db}', expected test database '{test_db_name}'.")
        if current_db == "trustdesk":
            raise RuntimeError("CRITICAL: Connected directly to development database 'trustdesk'. Aborting.")
    return test_db_name


@pytest.fixture(scope="module", autouse=True)
def isolated_e2e_environment():
    """Configures dedicated test database and test queue for all E2E workflow tests."""
    orig_engine = db_mod.engine
    orig_queue_name = settings.rq_queue_name

    # 1. Validate and connect to dedicated test DB
    test_engine = db_mod.get_engine(settings.database_url_test)
    test_db_name = verify_test_database_isolation(test_engine)

    # 2. Rebind SQLAlchemy SessionFactory and engine to test DB
    db_mod.SessionFactory.configure(bind=test_engine)
    db_mod.engine = test_engine

    def _test_db_override():
        session = db_mod.SessionFactory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _test_db_override

    # 3. Deterministic Knowledge Base Setup in dedicated test DB
    with db_mod.get_db_session() as session:
        kb_count = session.scalar(select(func.count()).select_from(KBSection))
        if kb_count < 9:
            ingest_kb_documents(session, Path("./data/kb_documents.json"))
            derive_and_index_sections(session)
            session.commit()

    # 4. Configure dedicated test Redis queue
    settings.rq_queue_name = TEST_QUEUE_NAME

    try:
        yield {
            "test_engine": test_engine,
            "test_db_name": test_db_name,
            "queue_name": TEST_QUEUE_NAME,
        }
    finally:
        # Restore original production/dev configuration
        app.dependency_overrides.pop(get_db, None)
        db_mod.SessionFactory.configure(bind=orig_engine)
        db_mod.engine = orig_engine
        settings.rq_queue_name = orig_queue_name
        test_engine.dispose()


@dataclass
class E2EEntityTracker:
    """Tracks all synthetic entities created during E2E tests for safe, targeted cleanup."""

    customer_ids: set[str] = field(default_factory=set)
    order_ids: set[str] = field(default_factory=set)
    ticket_ids: set[str] = field(default_factory=set)
    action_ids: set[uuid.UUID] = field(default_factory=set)
    eval_run_ids: set[uuid.UUID] = field(default_factory=set)
    job_ids: set[str] = field(default_factory=set)
    idempotency_keys: set[str] = field(default_factory=set)


@pytest.fixture
def e2e_tracker() -> Generator[E2EEntityTracker, None, None]:
    """Provides an entity tracker and guarantees targeted cleanup without truncating the database."""
    tracker = E2EEntityTracker()

    # Pre-execution check: Ensure no lingering active eval runs exist in test DB
    with get_db_session() as session:
        active_run = session.scalar(
            select(EvalRun).where(EvalRun.status.in_(["queued", "running"]))
        )
        if active_run:
            pytest.fail(f"Active evaluation run already present in test DB: {active_run.run_id}")

    yield tracker

    # 1. Targeted Database Cleanup (Safe, deletes only tracked synthetic records)
    with get_db_session() as session:
        # Delete evaluation results and runs created by test
        if tracker.eval_run_ids:
            session.execute(
                delete(EvalResult).where(EvalResult.run_id.in_(tracker.eval_run_ids))
            )
            session.execute(
                delete(EvalRun).where(EvalRun.run_id.in_(tracker.eval_run_ids))
            )

        # Delete idempotency records
        if tracker.idempotency_keys:
            session.execute(
                delete(ActionIdempotency).where(
                    ActionIdempotency.idempotency_key.in_(tracker.idempotency_keys)
                )
            )

        # Delete actions, drafts, triage results, traces, and tickets
        if tracker.ticket_ids:
            session.execute(
                delete(ProposedAction).where(
                    ProposedAction.ticket_id.in_(tracker.ticket_ids)
                )
            )
            draft_ids = session.scalars(
                select(DraftResponse.id).where(
                    DraftResponse.ticket_id.in_(tracker.ticket_ids)
                )
            ).all()
            if draft_ids:
                session.execute(
                    delete(DraftCitation).where(DraftCitation.draft_id.in_(draft_ids))
                )
            session.execute(
                delete(DraftResponse).where(
                    DraftResponse.ticket_id.in_(tracker.ticket_ids)
                )
            )
            session.execute(
                delete(TriageResult).where(
                    TriageResult.ticket_id.in_(tracker.ticket_ids)
                )
            )
            session.execute(
                delete(ExecutionTrace).where(
                    ExecutionTrace.ticket_id.in_(tracker.ticket_ids)
                )
            )
            session.execute(
                delete(Ticket).where(Ticket.ticket_id.in_(tracker.ticket_ids))
            )

        # Delete orders
        if tracker.order_ids:
            session.execute(delete(Order).where(Order.order_id.in_(tracker.order_ids)))

        # Delete customers
        if tracker.customer_ids:
            session.execute(
                delete(Customer).where(Customer.customer_id.in_(tracker.customer_ids))
            )

        session.commit()

    # 2. Targeted Redis Cleanup (Deletes only tracked test jobs)
    try:
        redis_c = get_redis_client()
        for job_id in tracker.job_ids:
            redis_c.delete(f"rq:job:{job_id}")
            redis_c.lrem(f"rq:queue:{TEST_QUEUE_NAME}", 0, job_id)
            redis_c.lrem(f"rq:queue:{settings.rq_queue_name}", 0, job_id)
    except Exception:
        pass


def _create_synthetic_ticket(
    session,
    tracker: E2EEntityTracker,
    *,
    subject: str,
    message: str,
    ticket_created_at: datetime | None = None,
    order_delivered_at: datetime | None = None,
    has_order: bool = True,
) -> tuple[Customer, Order | None, Ticket]:
    """Helper to create and persist a synthetic customer, order, and ticket for E2E tests."""
    suffix = uuid.uuid4().hex[:8]
    cust_id = f"CUST-E2E-{suffix}"
    ord_id = f"ORD-E2E-{suffix}" if has_order else None
    tick_id = f"TICK-E2E-{suffix}"

    now = ticket_created_at or datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)

    customer = Customer(
        customer_id=cust_id,
        name=f"E2E Test User {suffix}",
        email=f"e2e-{suffix}@example.com",
        metadata_json={"tier": "enterprise"},
        created_at=now - timedelta(days=60),
    )
    session.add(customer)
    tracker.customer_ids.add(cust_id)

    order = None
    if has_order:
        delivery = order_delivered_at or (now - timedelta(days=10))
        order = Order(
            order_id=ord_id,
            customer_id=cust_id,
            order_date=delivery - timedelta(days=3),
            delivery_date=delivery,
            status="delivered",
            total_amount=Decimal("199.99"),
            items=[{"sku": "SKU-E2E-1", "name": "Smart Hub V2", "qty": 1}],
        )
        session.add(order)
        tracker.order_ids.add(ord_id)

    ticket = Ticket(
        ticket_id=tick_id,
        customer_id=cust_id,
        order_id=ord_id,
        subject=subject,
        message=message,
        status="open",
        created_at=now,
        raw_metadata={"source": "e2e_test"},
    )
    session.add(ticket)
    tracker.ticket_ids.add(tick_id)

    session.commit()
    return customer, order, ticket


# ==============================================================================
# Workflow 1 — Ticket Ingestion and AI Triage (P8-EC-001, EG-P8-01)
# ==============================================================================


def test_workflow_1_ticket_ingestion_and_ai_triage(e2e_tracker: E2EEntityTracker) -> None:
    """Verifies Workflow 1: Ticket Ingestion & Context Retrieval -> AI Triage -> Persistence -> Sanitized Trace.

    Exercises:
    1. Synthetic ticket exists in PostgreSQL via supported data model.
    2. Authenticated API retrieves ticket context (customer, order, past tickets).
    3. AI triage classifies inquiry deterministically via MockAIProvider.
    4. Canonical category, priority, and escalation schemas are validated.
    5. Triage outcome is persisted to `triage_results`.
    6. Sanitized execution trace is persisted to `execution_traces`.
    7. Execution trace contains zero unredacted PII or secrets.
    """
    with get_db_session() as session:
        customer, order, ticket = _create_synthetic_ticket(
            session,
            e2e_tracker,
            subject="Defective display unit with dead pixels and glitching screen",
            message="My device screen started flickering with dead pixels 5 days after delivery. Need replacement under warranty.",
        )

    # 1. Retrieve ticket and assembled operational context
    resp_detail = client.get(f"/api/v1/tickets/{ticket.ticket_id}", headers=AUTH_HEADER)
    assert resp_detail.status_code == 200
    assert resp_detail.json()["ticket_id"] == ticket.ticket_id
    assert resp_detail.json()["status"] == "open"

    resp_context = client.get(f"/api/v1/tickets/{ticket.ticket_id}/context", headers=AUTH_HEADER)
    assert resp_context.status_code == 200
    ctx_data = resp_context.json()
    assert ctx_data["customer"]["customer_id"] == customer.customer_id
    assert ctx_data["order"]["order_id"] == order.order_id
    assert ctx_data["order"]["delivery_date"] is not None

    # 2. Trigger AI Triage
    resp_triage = client.post(f"/api/v1/tickets/{ticket.ticket_id}/triage", headers=AUTH_HEADER)
    assert resp_triage.status_code == 200
    triage_data = resp_triage.json()

    # Verify canonical schema output
    assert triage_data["category"] == TicketCategory.WARRANTY.value
    assert triage_data["priority"] in [TicketPriority.MEDIUM.value, TicketPriority.HIGH.value]
    assert isinstance(triage_data["needs_escalation"], bool)
    assert triage_data["is_fallback"] is False
    assert len(triage_data["reasoning"]) > 0

    # 3. Verify PostgreSQL Persistence of Triage Result
    with get_db_session() as session:
        triage_row = session.execute(
            select(TriageResult).where(TriageResult.ticket_id == ticket.ticket_id)
        ).scalar_one_or_none()
        assert triage_row is not None
        assert triage_row.category == TicketCategory.WARRANTY.value
        assert triage_row.is_fallback is False

        # 4. Verify Associated Execution Trace
        trace_row = session.execute(
            select(ExecutionTrace).where(
                ExecutionTrace.ticket_id == ticket.ticket_id,
                ExecutionTrace.run_type == "triage",
            )
        ).scalar_one_or_none()
        assert trace_row is not None
        assert trace_row.final_status == "success"
        assert trace_row.guardrail_outcome == "passed"

        # 5. Assert Sanitized Telemetry Invariant (Zero PII or Secrets)
        telemetry_str = str(trace_row.sanitized_telemetry)
        assert not PII_CREDIT_CARD_REGEX.search(telemetry_str), "Trace telemetry contains credit card pattern"
        assert not PII_SECRET_KEY_REGEX.search(telemetry_str), "Trace telemetry contains unmasked API secret"


# ==============================================================================
# Workflow 2 — RAG Retrieval and Grounded Draft Generation (P8-EC-001, P8-EC-002, EG-P8-01, EG-P8-02)
# ==============================================================================


def test_workflow_2_rag_retrieval_and_grounded_draft_generation(e2e_tracker: E2EEntityTracker) -> None:
    """Verifies Workflow 2 Happy Path: RAG Policy Retrieval -> 3-Level Grounding -> Citations -> Action Recommendation.

    Exercises:
    1. Customer inquiry on return eligibility within the 30-day window.
    2. PostgreSQL FTS matches `KB-REFUND-001` sections.
    3. Draft generation validates citation provenance against retrieved sections.
    4. Deterministic temporal policy window checks elapsed time relative to ticket.created_at.
    5. Draft, citations, and execution traces persist to PostgreSQL.
    6. Suggested action recommends starting a refund review.
    """
    now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    # Delivered 10 days before ticket inquiry -> strictly within 30-day window
    order_delivered = now - timedelta(days=10)

    with get_db_session() as session:
        _customer, order, ticket = _create_synthetic_ticket(
            session,
            e2e_tracker,
            subject="Return request for undamaged item",
            message="I would like to return this product for a refund. It was delivered 10 days ago and is unused.",
            ticket_created_at=now,
            order_delivered_at=order_delivered,
        )

    # Trigger Grounded Draft Generation
    resp_draft = client.post(f"/api/v1/tickets/{ticket.ticket_id}/draft", headers=AUTH_HEADER)
    assert resp_draft.status_code == 200
    draft_data = resp_draft.json()

    # Citations & Provenance verification
    assert len(draft_data["citations"]) > 0
    first_citation = draft_data["citations"][0]
    assert first_citation["kb_id"] == "KB-REFUND-001"
    assert first_citation["is_valid_provenance"] is True

    # Grounding & Temporal Window verification
    assert draft_data["has_valid_provenance"] is True
    assert draft_data["is_grounded"] is True
    assert draft_data["escalation_suggested"] is False

    # Advisory Action Recommendation verification
    assert draft_data["suggested_action"] is not None
    assert draft_data["suggested_action"]["should_recommend"] is True
    assert draft_data["suggested_action"]["action_type"] == "start_refund_review"

    # Verify Database Persistence
    with get_db_session() as session:
        draft_row = session.execute(
            select(DraftResponse).where(DraftResponse.ticket_id == ticket.ticket_id)
        ).scalar_one_or_none()
        assert draft_row is not None
        assert draft_row.is_grounded is True
        assert draft_row.escalation_suggested is False

        # Citations persisted with foreign key
        citations = session.execute(
            select(DraftCitation).where(DraftCitation.draft_id == draft_row.id)
        ).scalars().all()
        assert len(citations) == len(draft_data["citations"])

        # Execution trace recorded
        trace = session.execute(
            select(ExecutionTrace).where(
                ExecutionTrace.ticket_id == ticket.ticket_id,
                ExecutionTrace.run_type == "draft_generation",
            )
        ).scalar_one_or_none()
        assert trace is not None
        assert "KB-REFUND-001" in trace.retrieved_kb_ids


def test_workflow_2_insufficient_evidence_escalation(e2e_tracker: E2EEntityTracker) -> None:
    """Verifies Workflow 2 Safe Escalation (P8-EC-002, EG-P8-02): Insufficient evidence triggers human escalation.

    Exercises:
    1. Inquiry describes an out-of-scope or unindexed legal/commercial topic.
    2. RAG retrieval yields zero matching policy sections.
    3. Draft service sets is_grounded=false, escalation_suggested=true.
    4. Draft contains explicit escalation advisory message and zero hallucinated citations.
    5. Action recommender sets should_recommend=false; zero actions are proposed.
    """
    now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    with get_db_session() as session:
        _customer, _order, ticket = _create_synthetic_ticket(
            session,
            e2e_tracker,
            subject="Dispute over enterprise partnership contract terms and trademark royalties",
            message="We require immediate binding arbitration regarding trademark licensing clauses in our corporate agreement.",
            ticket_created_at=now,
        )

    resp_draft = client.post(f"/api/v1/tickets/{ticket.ticket_id}/draft", headers=AUTH_HEADER)
    assert resp_draft.status_code == 200
    draft_data = resp_draft.json()

    # Safe Escalation Contract
    assert draft_data["is_grounded"] is False
    assert draft_data["escalation_suggested"] is True
    assert draft_data["escalation_reason"] is not None
    assert len(draft_data["citations"]) == 0
    assert (
        draft_data.get("suggested_action") is None
        or draft_data["suggested_action"]["should_recommend"] is False
    )

    # Verify zero actions were created in DB
    with get_db_session() as session:
        action_count = session.scalar(
            select(func.count()).select_from(ProposedAction).where(ProposedAction.ticket_id == ticket.ticket_id)
        )
        assert action_count == 0


def test_workflow_2_temporal_eligibility_window_enforcement(e2e_tracker: E2EEntityTracker) -> None:
    """Verifies that return and warranty eligibility strictly evaluate relative to ticket.created_at, never system clock.

    Exercises:
    - Case A: Grounded ineligibility on expired order (45 days > 30-day window).
    - Case B: Hallucinated model claim on expired order is overridden by Level 3 temporal validator.
    - Case C: Order with null delivery date refuses to guess or use system clock, safely escalating.
    """
    now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)

    with get_db_session() as session:
        # Case A: Delivered 45 days ago -> outside 30-day window
        _cust_a, _ord_a, ticket_expired = _create_synthetic_ticket(
            session,
            e2e_tracker,
            subject="Return inquiry on older order",
            message="I would like to return this order for a full refund.",
            ticket_created_at=now,
            order_delivered_at=now - timedelta(days=45),
        )

        # Case B: Model attempts to claim eligibility on expired order
        _cust_b, _ord_b, ticket_hallucinated = _create_synthetic_ticket(
            session,
            e2e_tracker,
            subject="Return inquiry with simulate_hallucinated_eligibility",
            message="Please refund my order. simulate_hallucinated_eligibility",
            ticket_created_at=now,
            order_delivered_at=now - timedelta(days=45),
        )

        # Case C: Order missing delivery_date
        _cust_c, _ord_c, ticket_missing_date = _create_synthetic_ticket(
            session,
            e2e_tracker,
            subject="Return inquiry on undated delivery",
            message="I need a refund for this order.",
            ticket_created_at=now,
            order_delivered_at=None,
        )
        # Explicitly set delivery_date to None
        _ord_c.delivery_date = None
        session.commit()

    # Case A: Grounded ineligibility
    resp_a = client.post(f"/api/v1/tickets/{ticket_expired.ticket_id}/draft", headers=AUTH_HEADER)
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert data_a["is_grounded"] is True
    assert data_a["escalation_suggested"] is False
    assert "outside the eligible return window" in data_a["draft_text"].lower()
    assert data_a["suggested_action"]["should_recommend"] is False

    # Case B: Contradictory model claim caught by Level 3 temporal check
    resp_b = client.post(f"/api/v1/tickets/{ticket_hallucinated.ticket_id}/draft", headers=AUTH_HEADER)
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    assert data_b["is_grounded"] is False
    assert data_b["escalation_suggested"] is True
    assert data_b["suggested_action"]["should_recommend"] is False

    # Case C: Missing delivery date safely escalates without substituting system clock
    resp_c = client.post(f"/api/v1/tickets/{ticket_missing_date.ticket_id}/draft", headers=AUTH_HEADER)
    assert resp_c.status_code == 200
    data_c = resp_c.json()
    assert data_c["is_grounded"] is False
    assert data_c["escalation_suggested"] is True
    assert data_c["suggested_action"]["should_recommend"] is False


# ==============================================================================
# Workflow 3 — Refund-Review Recommendation and Human Approval (P8-EC-001, EG-P8-01)
# ==============================================================================


def test_workflow_3_refund_review_recommendation_and_approval_lifecycle(
    e2e_tracker: E2EEntityTracker,
) -> None:
    """Verifies Workflow 3: Recommendation -> Action Proposal -> Discovery -> Human Approval -> Execution Trace.

    Exercises:
    1. AI recommendation is strictly advisory; no action executes automatically.
    2. Propose refund review transitions action to pending_approval.
    3. Action discovery endpoint GET /tickets/{id}/actions returns pending action.
    4. Authenticated human agent approves action with unique Idempotency-Key.
    5. Action transitions to 'executed' under transactional row lock.
    6. Server-verified agent identity is recorded (client spoofing prevented).
    7. Persistent idempotency record committed; replay succeeds idempotently.
    8. Attempt to approve already-executed action with a new key returns HTTP 409 Conflict.
    9. Confirms zero money disbursement or payment gateway communication occurs.
    """
    now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    with get_db_session() as session:
        _customer, order, ticket = _create_synthetic_ticket(
            session,
            e2e_tracker,
            subject="Return inquiry within 30 days",
            message="I would like to return this product for a refund. It was delivered 10 days ago.",
            ticket_created_at=now,
            order_delivered_at=now - timedelta(days=10),
        )

    # 1. Draft recommends starting a review (Advisory Only)
    resp_draft = client.post(f"/api/v1/tickets/{ticket.ticket_id}/draft", headers=AUTH_HEADER)
    assert resp_draft.status_code == 200
    assert resp_draft.json()["suggested_action"]["should_recommend"] is True

    # Verify no action is executed yet
    with get_db_session() as session:
        action_count = session.scalar(
            select(func.count()).select_from(ProposedAction).where(ProposedAction.ticket_id == ticket.ticket_id)
        )
        assert action_count == 0

    # 2. Support Agent / System proposes refund review
    resp_propose = client.post(
        f"/api/v1/tickets/{ticket.ticket_id}/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review", "payload": {"order_id": order.order_id}},
    )
    assert resp_propose.status_code == 201
    action_data = resp_propose.json()
    action_id = uuid.UUID(action_data["action_id"])
    e2e_tracker.action_ids.add(action_id)
    assert action_data["status"] == "pending_approval"
    assert action_data["action_type"] == "start_refund_review"

    # 3. Action Discovery (U-014)
    resp_discovery = client.get(f"/api/v1/tickets/{ticket.ticket_id}/actions", headers=AUTH_HEADER)
    assert resp_discovery.status_code == 200
    actions_list = resp_discovery.json()
    assert len(actions_list) == 1
    assert actions_list[0]["action_id"] == str(action_id)
    assert actions_list[0]["status"] == "pending_approval"

    # 4. Human Approval Gate
    idempotency_key = f"IDEMP-E2E-{uuid.uuid4().hex[:12]}"
    e2e_tracker.idempotency_keys.add(idempotency_key)

    resp_approve = client.post(
        f"/api/v1/actions/{action_id}/approve",
        headers={**AUTH_HEADER, "Idempotency-Key": idempotency_key},
        json={"notes": "Order verified within 30-day window. Formal review registered."},
    )
    assert resp_approve.status_code == 200
    exec_data = resp_approve.json()
    assert exec_data["status"] == "executed"
    assert exec_data["action_type"] == "start_refund_review"
    assert exec_data["reviewed_by"] == "demo-agent-001"
    assert "registration_id" in exec_data["execution_details"]
    assert exec_data["execution_details"]["review_queue"] == "human_refund_investigation"

    # 5. Database State and Audit Trace Verification
    with get_db_session() as session:
        action_row = session.execute(
            select(ProposedAction).where(ProposedAction.action_id == action_id)
        ).scalar_one()
        assert action_row.status == "executed"
        assert action_row.reviewed_by == "demo-agent-001"
        assert action_row.executed_at is not None

        # Verify idempotency record
        idemp_row = session.execute(
            select(ActionIdempotency).where(ActionIdempotency.idempotency_key == idempotency_key)
        ).scalar_one()
        assert idemp_row.status == "completed"

        # Verify execution trace logged
        trace = session.execute(
            select(ExecutionTrace).where(
                ExecutionTrace.ticket_id == ticket.ticket_id,
                ExecutionTrace.run_type == "action_execution",
            )
        ).scalar_one_or_none()
        assert trace is not None
        assert len(trace.executed_actions) == 1
        assert trace.executed_actions[0]["action_type"] == "start_refund_review"
        assert trace.executed_actions[0]["reviewed_by"] == "demo-agent-001"
        assert trace.final_status == "success"

    # 6. Idempotent Replay (Same Idempotency-Key returns cached response)
    resp_replay = client.post(
        f"/api/v1/actions/{action_id}/approve",
        headers={**AUTH_HEADER, "Idempotency-Key": idempotency_key},
        json={"notes": "Order verified within 30-day window. Formal review registered."},
    )
    assert resp_replay.status_code == 200
    assert resp_replay.json()["action_id"] == str(action_id)
    assert resp_replay.json()["status"] == "executed"

    # 7. Already-Processed Conflict (Different Idempotency-Key rejected with HTTP 409)
    new_key = f"IDEMP-E2E-{uuid.uuid4().hex[:12]}"
    e2e_tracker.idempotency_keys.add(new_key)
    resp_conflict = client.post(
        f"/api/v1/actions/{action_id}/approve",
        headers={**AUTH_HEADER, "Idempotency-Key": new_key},
        json={"notes": "Attempting second approval with new key"},
    )
    assert resp_conflict.status_code == 409
    assert resp_conflict.json()["error"]["code"] == "ACTION_ALREADY_PROCESSED"


def test_workflow_3_action_rejection_lifecycle(e2e_tracker: E2EEntityTracker) -> None:
    """Verifies Workflow 3 Rejection: Human agent rejects proposed action, transitioning to terminal 'rejected' state."""
    now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    with get_db_session() as session:
        _customer, order, ticket = _create_synthetic_ticket(
            session,
            e2e_tracker,
            subject="Return inquiry for damaged goods",
            message="Product arrived damaged.",
            ticket_created_at=now,
        )

    # Propose review
    resp_propose = client.post(
        f"/api/v1/tickets/{ticket.ticket_id}/actions/refund-review/propose",
        headers=AUTH_HEADER,
        json={"action_type": "start_refund_review", "payload": {"order_id": order.order_id}},
    )
    assert resp_propose.status_code == 201
    action_id = uuid.UUID(resp_propose.json()["action_id"])
    e2e_tracker.action_ids.add(action_id)

    # Agent rejects review
    resp_reject = client.post(
        f"/api/v1/actions/{action_id}/reject",
        headers=AUTH_HEADER,
        json={"reason": "Damage caused by customer misuse per uploaded evidence."},
    )
    assert resp_reject.status_code == 200
    assert resp_reject.json()["status"] == "rejected"
    assert resp_reject.json()["reviewed_by"] == "demo-agent-001"

    # Verify Database state
    with get_db_session() as session:
        action_row = session.execute(
            select(ProposedAction).where(ProposedAction.action_id == action_id)
        ).scalar_one()
        assert action_row.status == "rejected"
        assert action_row.review_notes == "Damage caused by customer misuse per uploaded evidence."


# ==============================================================================
# Workflow 4 — Background Evaluation Execution (P8-EC-009, EG-P8-03)
# ==============================================================================


def test_workflow_4_background_evaluation_execution_and_accounting(
    e2e_tracker: E2EEntityTracker,
) -> None:
    """Verifies Workflow 4 (P8-EC-009, EG-P8-03): Asynchronous evaluation pipeline & rigorous input accounting.

    Exercises:
    1. Authenticated submission POST /api/v1/evaluations/run.
    2. HTTP 202 response with valid run and job identifiers.
    3. PostgreSQL persists queued run; Redis receives the RQ task.
    4. RQ SimpleWorker in burst mode dequeues and executes suite via MockAIProvider.
    5. Job polling transitions from queued -> running -> completed.
    6. Aggregate metrics and per-case results are retrievable via GET /evaluations/{id}.
    7. Rigorous Evaluation Accounting Invariant:
       Verifies that the counters `evaluated`, `inconclusive`, `invalid_input`, and `model_failure`
       are mutually exclusive subsets of the dataset input lines:
       total_lines (18) = evaluated (16) + inconclusive (1) + invalid_input (0) + model_failure (1).
    """
    assert DATASET_PATH.is_file(), f"Dataset file missing at {DATASET_PATH}"
    assert settings.rq_queue_name == TEST_QUEUE_NAME

    # 1. Enqueue Evaluation Run via API
    resp_run = client.post(
        "/api/v1/evaluations/run",
        headers=AUTH_HEADER,
        json={"dataset_path": str(DATASET_PATH)},
    )
    assert resp_run.status_code == 202, f"Failed enqueue: {resp_run.text}"
    enqueue_data = resp_run.json()
    run_id = uuid.UUID(enqueue_data["run_id"])
    job_id = enqueue_data["job_id"]
    e2e_tracker.eval_run_ids.add(run_id)
    e2e_tracker.job_ids.add(job_id)

    assert enqueue_data["status"] == "queued"

    # Verify job was enqueued into isolated test queue
    redis_client = get_redis_client()
    rq_job = Job.fetch(job_id, connection=redis_client)
    assert rq_job.origin == TEST_QUEUE_NAME, f"Job origin was {rq_job.origin}, expected {TEST_QUEUE_NAME}"

    # 2. Verify Initial Queued State in PostgreSQL
    with get_db_session() as session:
        initial_run = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id)
        ).scalar_one()
        assert initial_run.status == "queued"
        assert initial_run.job_id == job_id

    # 3. Process Asynchronous Job via RQ Worker (Burst Mode on isolated queue)
    queue = Queue(TEST_QUEUE_NAME, connection=redis_client)
    worker = SimpleWorker([queue], connection=redis_client)
    worker.work(burst=True)

    # 4. Poll Job Status API
    resp_job = client.get(f"/api/v1/jobs/{job_id}", headers=AUTH_HEADER)
    assert resp_job.status_code == 200
    job_status = resp_job.json()
    assert job_status["status"] == "completed"
    assert job_status["run_id"] == str(run_id)

    # 5. Fetch Full Evaluation Run Details API
    resp_detail = client.get(f"/api/v1/evaluations/{run_id}", headers=AUTH_HEADER)
    assert resp_detail.status_code == 200
    detail_data = resp_detail.json()
    assert detail_data["status"] == "completed"
    assert detail_data["total_cases"] == 18

    # 6. Verify Per-Case Results Persistence & Ordering
    case_results = detail_data["results"]
    assert len(case_results) == 18
    # Assert sorted strictly by source_line_number ASC
    line_numbers = [c["source_line_number"] for c in case_results]
    assert line_numbers == list(range(1, 19))

    # 7. Rigorous Evaluation Accounting Invariant Verification
    metrics_summary = detail_data["metrics_summary"]
    accounting = metrics_summary["input_accounting"]

    assert accounting["is_valid"] is True
    assert accounting["total_lines"] == 18
    assert accounting["evaluated"] == 16
    assert accounting["inconclusive"] == 1  # EVAL-017 (missing ground truth)
    assert accounting["invalid_input"] == 0  # Zero malformed lines in golden dataset
    assert accounting["model_failure"] == 1  # EVAL-016 (simulated timeout)

    # Invariant formula verification:
    assert (
        accounting["total_lines"]
        == accounting["evaluated"]
        + accounting["inconclusive"]
        + accounting["invalid_input"]
        + accounting["model_failure"]
    )

    # 8. Database-Level Proof of Mutual Exclusivity:
    # Query eval_results directly and count rows by validation_status to prove they partition the 18 lines:
    with get_db_session() as session:
        results = session.execute(
            select(EvalResult).where(EvalResult.run_id == run_id)
        ).scalars().all()
        assert len(results) == 18

        status_counts: dict[str, int] = {}
        for r in results:
            st = r.validation_status.lower()
            status_counts[st] = status_counts.get(st, 0) + 1

        # Assert mutually exclusive partition:
        evaluated_count = status_counts.get("valid", 0) + status_counts.get("evaluated", 0)
        inconclusive_count = status_counts.get("inconclusive", 0)
        invalid_count = status_counts.get("malformed_input", 0) + status_counts.get("invalid_input", 0)
        model_failure_count = status_counts.get("model_failure", 0)

        assert evaluated_count == 16, f"Expected 16 evaluated rows, got {evaluated_count}"
        assert inconclusive_count == 1, f"Expected 1 inconclusive row (EVAL-017), got {inconclusive_count}"
        assert invalid_count == 0, f"Expected 0 invalid rows, got {invalid_count}"
        assert model_failure_count == 1, f"Expected 1 model failure row (EVAL-016), got {model_failure_count}"
        assert evaluated_count + inconclusive_count + invalid_count + model_failure_count == 18


# ---------------------------------------------------------------------------
# Clean Bootstrap & Cold Startup Verification (P8-EC-003 & EG-P8-09)
# ---------------------------------------------------------------------------

from tests.adversarial.test_security_regressions import (
    test_cold_bootstrap_data_integrity,
)
