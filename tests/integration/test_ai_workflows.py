from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from trustdesk.core.config import settings
from trustdesk.core.database import Base, engine, get_db_session
from trustdesk.main import app
from trustdesk.models.ai import DraftCitation, DraftResponse, ExecutionTrace, TriageResult
from trustdesk.models.customer import Customer
from trustdesk.models.knowledge import KBSection, KnowledgeDocument
from trustdesk.models.order import Order
from trustdesk.models.ticket import Ticket
from trustdesk.services.knowledge_service import derive_and_index_sections

client = TestClient(app)
AUTH_HEADER = {"Authorization": f"Bearer {settings.trustdesk_demo_token}"}


@pytest.fixture(autouse=True)
def clean_database():
    """Ensure database schema is clean and fresh before each integration test."""
    Base.metadata.create_all(bind=engine)
    with get_db_session() as session:
        session.execute(
            text(
                "TRUNCATE TABLE draft_citations, draft_responses, triage_results, "
                "execution_traces, kb_sections, kb_documents, quarantined_records, "
                "tickets, orders, customers CASCADE;"
            )
        )
        session.commit()
    yield


def _seed_test_domain_data() -> dict[str, str]:
    """Helper to seed customer, orders, tickets, and knowledge base sections."""
    now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    order_delivered_recent = now - timedelta(days=15)   # Within 30-day window
    order_delivered_expired = now - timedelta(days=45)  # Outside 30-day window

    with get_db_session() as session:
        # Customer
        customer = Customer(
            customer_id="CUST-AI-001",
            name="Sarah Connor",
            email="sarah@example.com",
            metadata_json={"tier": "premium"},
            created_at=now,
        )
        session.add(customer)

        # Orders
        order_valid = Order(
            order_id="ORD-VALID-01",
            customer_id="CUST-AI-001",
            order_date=order_delivered_recent - timedelta(days=3),
            delivery_date=order_delivered_recent,
            status="delivered",
            total_amount=Decimal("120.00"),
            items=[{"sku": "HW-001", "name": "Smart Router", "qty": 1}],
        )
        order_expired = Order(
            order_id="ORD-EXPIRED-02",
            customer_id="CUST-AI-001",
            order_date=order_delivered_expired - timedelta(days=3),
            delivery_date=order_delivered_expired,
            status="delivered",
            total_amount=Decimal("250.00"),
            items=[{"sku": "HW-002", "name": "Laser Mouse", "qty": 1}],
        )
        order_no_delivery = Order(
            order_id="ORD-NO-DELIV-03",
            customer_id="CUST-AI-001",
            order_date=now - timedelta(days=5),
            delivery_date=None,
            status="in_transit",
            total_amount=Decimal("80.00"),
            items=[{"sku": "HW-003", "name": "USB Hub", "qty": 1}],
        )
        session.add_all([order_valid, order_expired, order_no_delivery])

        # Tickets
        # 1. Valid refund within 30-day window
        ticket_refund_valid = Ticket(
            ticket_id="TIK-REFUND-VALID",
            customer_id="CUST-AI-001",
            order_id="ORD-VALID-01",
            subject="Return inquiry for Smart Router",
            message="I would like to return this smart router for a full refund.",
            status="open",
            created_at=now,
        )
        # 2. Expired refund (> 30 days)
        ticket_refund_expired = Ticket(
            ticket_id="TIK-REFUND-EXPIRED",
            customer_id="CUST-AI-001",
            order_id="ORD-EXPIRED-02",
            subject="Refund request for Laser Mouse",
            message="Can I get a refund on my laser mouse order?",
            status="open",
            created_at=now,
        )
        # 3. Expired refund with model simulating hallucinated eligibility
        ticket_hallucinated_eligibility = Ticket(
            ticket_id="TIK-HALLUCINATED-ELIG",
            customer_id="CUST-AI-001",
            order_id="ORD-EXPIRED-02",
            subject="Refund request simulate_hallucinated_eligibility",
            message="I demand a return for my order simulate_hallucinated_eligibility.",
            status="open",
            created_at=now,
        )
        # 4. Refund with missing delivery date
        ticket_no_delivery = Ticket(
            ticket_id="TIK-NO-DELIVERY",
            customer_id="CUST-AI-001",
            order_id="ORD-NO-DELIV-03",
            subject="Refund inquiry for in-transit package",
            message="I want to cancel and refund my USB Hub.",
            status="open",
            created_at=now,
        )
        # 5. Refund ticket with null order_id
        ticket_null_order = Ticket(
            ticket_id="TIK-NULL-ORDER",
            customer_id="CUST-AI-001",
            order_id=None,
            subject="Return inquiry no order specified",
            message="I need to return an item I bought last week for a refund.",
            status="open",
            created_at=now,
        )
        # 6. Security incident
        ticket_security = Ticket(
            ticket_id="TIK-SECURITY-01",
            customer_id="CUST-AI-001",
            order_id=None,
            subject="Account hacked and password changed",
            message="Someone breached my account and changed my password! Unauthorized access detected.",
            status="open",
            created_at=now,
        )
        # 7. Unrelated topic (zero policy matches)
        ticket_unrelated = Ticket(
            ticket_id="TIK-UNRELATED-01",
            customer_id="CUST-AI-001",
            order_id=None,
            subject="How do I cook lasagna at home?",
            message="Looking for a good recipe to bake lasagna for dinner.",
            status="open",
            created_at=now,
        )
        # 8. Timeout simulation
        ticket_timeout = Ticket(
            ticket_id="TIK-TIMEOUT-01",
            customer_id="CUST-AI-001",
            order_id="ORD-VALID-01",
            subject="Refund inquiry simulate_timeout",
            message="Please process return simulate_timeout.",
            status="open",
            created_at=now,
        )
        # 9. Malformed simulation
        ticket_malformed = Ticket(
            ticket_id="TIK-MALFORMED-01",
            customer_id="CUST-AI-001",
            order_id="ORD-VALID-01",
            subject="Refund inquiry simulate_malformed",
            message="Broken return message simulate_malformed.",
            status="open",
            created_at=now,
        )
        # 10. Hallucinated citation simulation
        ticket_bad_citation = Ticket(
            ticket_id="TIK-BAD-CITATION",
            customer_id="CUST-AI-001",
            order_id="ORD-VALID-01",
            subject="Return inquiry simulate_hallucinated_citation",
            message="Process return simulate_hallucinated_citation.",
            status="open",
            created_at=now,
        )
        # 11. Unauthorized discount simulation
        ticket_discount = Ticket(
            ticket_id="TIK-DISCOUNT-01",
            customer_id="CUST-AI-001",
            order_id="ORD-VALID-01",
            subject="Refund inquiry simulate_unauthorized_discount",
            message="I am unhappy with service simulate_unauthorized_discount.",
            status="open",
            created_at=now,
        )

        session.add_all([
            ticket_refund_valid,
            ticket_refund_expired,
            ticket_hallucinated_eligibility,
            ticket_no_delivery,
            ticket_null_order,
            ticket_security,
            ticket_unrelated,
            ticket_timeout,
            ticket_malformed,
            ticket_bad_citation,
            ticket_discount,
        ])

        # Knowledge Base Documents & Sectioning
        doc_refund = KnowledgeDocument(
            kb_id="KB-REFUND-001",
            title="Standard Return and Refund Policy",
            category="refund",
            raw_content=(
                "# Standard Return and Refund Policy\n\n"
                "## 1. Overview and Eligibility Window\n"
                "Customers may return eligible hardware products within 30 calendar days from the date of confirmed delivery. "
                "The return window is strictly calculated from the delivery date recorded in the customer's order history to the ticket creation date.\n\n"
                "## 2. Product Condition and Requirements\n"
                "Items must be returned in their original packaging, including all accessories, cables, and manuals.\n\n"
                "## 3. Refund Review and Human Approval\n"
                "Any refund action recommended by support automation must undergo human review by an authenticated support agent via the `start_refund_review` process."
            ),
            updated_at=now,
        )
        doc_war = KnowledgeDocument(
            kb_id="KB-WAR-002",
            title="Hardware Limited Warranty Policy",
            category="warranty",
            raw_content=(
                "# Hardware Limited Warranty Policy\n\n"
                "## 1. Warranty Duration and Scope\n"
                "All electronic hardware devices purchased through authorized channels include a 1-year (365 calendar days) limited manufacturer warranty starting from the confirmed date of delivery.\n\n"
                "## 2. Covered Hardware Defects\n"
                "This warranty covers defects in materials and workmanship under normal consumer use."
            ),
            updated_at=now,
        )
        doc_ship = KnowledgeDocument(
            kb_id="KB-SHIPPING-001",
            title="Shipping and Delivery SLA",
            category="shipping",
            raw_content=(
                "# Shipping and Delivery SLA\n\n"
                "## 1. Fulfillment Timelines\n"
                "Standard shipping orders are dispatched within 1 to 2 business days from order placement."
            ),
            updated_at=now,
        )
        session.add_all([doc_refund, doc_war, doc_ship])
        session.flush()

        derive_and_index_sections(session=session)

        session.commit()

    return {"ticket_id": "TIK-REFUND-VALID"}


# --- Triage Tests ---


def test_authenticated_triage_endpoint_success():
    """Verify POST /api/v1/tickets/{id}/triage executes successfully with valid auth."""
    _seed_test_domain_data()
    response = client.post("/api/v1/tickets/TIK-REFUND-VALID/triage", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["category"] == "refund"
    assert data["priority"] in ["medium", "high", "urgent"]
    assert data["needs_escalation"] is False
    assert data["is_fallback"] is False
    assert "refund" in data["reasoning"].lower()

    # Verify database persistence
    with get_db_session() as session:
        triage_rec = session.query(TriageResult).filter_by(ticket_id="TIK-REFUND-VALID").first()
        assert triage_rec is not None
        assert triage_rec.category == "refund"

        trace = session.query(ExecutionTrace).filter_by(ticket_id="TIK-REFUND-VALID", run_type="triage").first()
        assert trace is not None
        assert trace.final_status == "success"
        assert trace.guardrail_outcome == "passed"


def test_unauthenticated_triage_rejected():
    """Verify POST /api/v1/tickets/{id}/triage rejects unauthenticated requests with HTTP 401."""
    _seed_test_domain_data()
    response = client.post("/api/v1/tickets/TIK-REFUND-VALID/triage")
    assert response.status_code == 401


def test_triage_nonexistent_ticket_returns_404():
    """Verify triage on a non-existent ticket returns HTTP 404."""
    _seed_test_domain_data()
    response = client.post("/api/v1/tickets/NON-EXISTENT/triage", headers=AUTH_HEADER)
    assert response.status_code == 404


def test_triage_account_security_escalation():
    """Verify security breaches are classified as account_security with needs_escalation=True."""
    _seed_test_domain_data()
    response = client.post("/api/v1/tickets/TIK-SECURITY-01/triage", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["category"] == "account_security"
    assert data["priority"] == "urgent"
    assert data["needs_escalation"] is True


def test_triage_simulated_timeout_fallback():
    """Verify timeout triggers safe fallback triage object with HTTP 200 and AI failure trace."""
    _seed_test_domain_data()
    response = client.post("/api/v1/tickets/TIK-TIMEOUT-01/triage", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["is_fallback"] is True
    assert data["category"] == "general"
    assert data["priority"] == "medium"
    assert data["needs_escalation"] is True
    assert "fallback" in data["reasoning"].lower()

    with get_db_session() as session:
        trace = session.query(ExecutionTrace).filter_by(ticket_id="TIK-TIMEOUT-01", run_type="triage").first()
        assert trace is not None
        assert trace.final_status == "failed"
        assert trace.guardrail_outcome == "escalated"


# --- Grounded Draft Tests ---


def test_authenticated_draft_endpoint_refund_within_window():
    """Verify draft generation for eligible refund produces grounded draft and citations."""
    _seed_test_domain_data()
    response = client.post("/api/v1/tickets/TIK-REFUND-VALID/draft", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["ticket_id"] == "TIK-REFUND-VALID"
    assert data["has_valid_provenance"] is True
    assert data["is_grounded"] is True
    assert data["escalation_suggested"] is False
    assert len(data["citations"]) > 0
    assert data["citations"][0]["kb_id"] == "KB-REFUND-001"
    assert data["suggested_action"] is not None
    assert data["suggested_action"]["should_recommend"] is True
    assert data["suggested_action"]["action_type"] == "start_refund_review"

    # Verify database persistence
    with get_db_session() as session:
        draft_rec = session.query(DraftResponse).filter_by(ticket_id="TIK-REFUND-VALID").first()
        assert draft_rec is not None
        assert draft_rec.is_grounded is True
        assert len(draft_rec.citations) > 0

        trace = session.query(ExecutionTrace).filter_by(ticket_id="TIK-REFUND-VALID", run_type="draft_generation").first()
        assert trace is not None
        assert trace.final_status == "success"
        assert "KB-REFUND-001" in trace.retrieved_kb_ids


def test_draft_grounded_ineligibility_on_expired_order():
    """Verify draft explaining ineligibility on an expired order is 100% grounded (U-002)."""
    _seed_test_domain_data()
    response = client.post("/api/v1/tickets/TIK-REFUND-EXPIRED/draft", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["has_valid_provenance"] is True
    assert data["is_grounded"] is True
    assert data["escalation_suggested"] is False
    assert data["suggested_action"]["should_recommend"] is False
    assert "outside the eligible return window" in data["draft_text"].lower()


def test_draft_claims_eligibility_on_expired_order_flagged_ungrounded():
    """Verify Level 3 detects contradiction when model claims eligibility on expired order."""
    _seed_test_domain_data()
    response = client.post("/api/v1/tickets/TIK-HALLUCINATED-ELIG/draft", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["has_valid_provenance"] is True
    # Level 3 contradiction flags it as ungrounded!
    assert data["is_grounded"] is False
    assert data["escalation_suggested"] is True
    assert "exceeding 30-day window" in data["escalation_reason"]


def test_draft_hallucinated_citation_rejected():
    """Verify Level 1 flags unretrieved citation reference and marks draft ungrounded."""
    _seed_test_domain_data()
    response = client.post("/api/v1/tickets/TIK-BAD-CITATION/draft", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["has_valid_provenance"] is False
    assert data["is_grounded"] is False
    assert data["escalation_suggested"] is True


def test_draft_unauthorized_discount_flagged():
    """Verify Level 2 discount scan detects promotional promise unsupported by policy."""
    _seed_test_domain_data()
    response = client.post("/api/v1/tickets/TIK-DISCOUNT-01/draft", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["is_grounded"] is False
    assert data["escalation_suggested"] is True
    assert "promotional discount unsupported" in data["escalation_reason"].lower()


def test_draft_missing_delivery_date_escalates():
    """Verify inquiry on order without delivery date escalates to human review (U-005)."""
    _seed_test_domain_data()
    response = client.post("/api/v1/tickets/TIK-NO-DELIVERY/draft", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["escalation_suggested"] is True
    assert data["is_grounded"] is False
    assert "delivery date is missing" in data["escalation_reason"].lower()


def test_draft_null_order_id_escalates():
    """Verify refund inquiry without linked order escalates to human review (U-005)."""
    _seed_test_domain_data()
    response = client.post("/api/v1/tickets/TIK-NULL-ORDER/draft", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["escalation_suggested"] is True
    assert data["is_grounded"] is False
    assert "no linked order record" in data["escalation_reason"].lower()


def test_draft_insufficient_evidence_escalates():
    """Verify inquiry with zero matching policy evidence triggers escalation notice."""
    _seed_test_domain_data()
    response = client.post("/api/v1/tickets/TIK-UNRELATED-01/draft", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["escalation_suggested"] is True
    assert data["is_grounded"] is False
    assert "insufficient policy evidence" in data["draft_text"].lower()


def test_draft_provider_timeout_returns_504():
    """Verify provider timeout on draft endpoint returns HTTP 504 and logs trace."""
    _seed_test_domain_data()
    response = client.post("/api/v1/tickets/TIK-TIMEOUT-01/draft", headers=AUTH_HEADER)
    assert response.status_code == 504
    assert "timed out after 15 seconds" in response.json()["error"]["message"]

    with get_db_session() as session:
        trace = session.query(ExecutionTrace).filter_by(ticket_id="TIK-TIMEOUT-01", run_type="draft_generation").first()
        assert trace is not None
        assert trace.final_status == "failed"


def test_draft_provider_malformed_returns_502():
    """Verify provider malformed/upstream failure on draft endpoint returns HTTP 502."""
    _seed_test_domain_data()
    response = client.post("/api/v1/tickets/TIK-MALFORMED-01/draft", headers=AUTH_HEADER)
    assert response.status_code == 502
    assert "error" in response.json()

    with get_db_session() as session:
        trace = session.query(ExecutionTrace).filter_by(ticket_id="TIK-MALFORMED-01", run_type="draft_generation").first()
        assert trace is not None
        assert trace.final_status == "failed"


def test_trace_sanitization_no_credentials_or_secrets():
    """Verify execution_traces never contain raw demo tokens, credentials, or secrets."""
    _seed_test_domain_data()
    client.post("/api/v1/tickets/TIK-REFUND-VALID/triage", headers=AUTH_HEADER)
    client.post("/api/v1/tickets/TIK-REFUND-VALID/draft", headers=AUTH_HEADER)

    with get_db_session() as session:
        traces = session.query(ExecutionTrace).all()
        assert len(traces) >= 2
        for t in traces:
            telemetry_str = str(t.sanitized_telemetry)
            assert settings.trustdesk_demo_token not in telemetry_str
            assert "SECRET-KEY-ALPHA-9999" not in telemetry_str
