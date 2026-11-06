from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from trustdesk.core.config import settings
from trustdesk.core.database import Base, engine, get_db, get_db_session
from trustdesk.main import app
from trustdesk.models.customer import Customer
from trustdesk.models.order import Order
from trustdesk.models.ticket import Ticket

client = TestClient(app)
AUTH_HEADER = {"Authorization": f"Bearer {settings.trustdesk_demo_token}"}


@pytest.fixture(autouse=True)
def clean_database():
    """Ensure database schema is clean and fresh before each integration test."""
    Base.metadata.create_all(bind=engine)
    with get_db_session() as session:
        session.execute(text("TRUNCATE TABLE quarantined_records, tickets, orders, customers, kb_documents CASCADE;"))
        session.commit()
    yield


def _seed_test_data() -> dict[str, str]:
    """Helper to seed customer, orders, and tickets for context verification."""
    now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    with get_db_session() as session:
        # Customers
        cust1 = Customer(
            customer_id="CUST-001",
            name="Alice Walker",
            email="alice@example.com",
            metadata_json={"vip": True},
            created_at=now,
        )
        cust2 = Customer(
            customer_id="CUST-002",
            name="Bob Brown",
            email="bob@example.com",
            metadata_json={"vip": False},
            created_at=now,
        )
        session.add_all([cust1, cust2])

        # Orders
        ord1 = Order(
            order_id="ORD-001",
            customer_id="CUST-001",
            order_date=now,
            delivery_date=now,
            status="delivered",
            total_amount=Decimal("150.00"),
            items=[{"sku": "SKU-A", "name": "Wireless Headphones", "price": 150.00, "qty": 1}],
        )
        session.add(ord1)

        # Tickets for Cust 1
        tik1 = Ticket(
            ticket_id="TIK-001",
            customer_id="CUST-001",
            order_id="ORD-001",
            subject="Headphones arrived defective",
            message="Right earbud has no audio.",
            status="open",
            created_at=datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc),
            raw_metadata={"priority": "high"},
        )
        tik2 = Ticket(
            ticket_id="TIK-002",
            customer_id="CUST-001",
            order_id=None,
            subject="General warranty question",
            message="What is the standard warranty duration?",
            status="closed",
            created_at=datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc),
            raw_metadata={},
        )

        # Ticket with quarantined unresolved reference for Cust 2
        tik3 = Ticket(
            ticket_id="TIK-003",
            customer_id="CUST-002",
            order_id=None,
            subject="Order status query",
            message="Where is my shipment?",
            status="open",
            created_at=datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc),
            raw_metadata={"unresolved_order_id": "ORD-MISSING-999"},
        )

        session.add_all([tik1, tik2, tik3])
        session.commit()

    return {"cust1": "CUST-001", "cust2": "CUST-002", "tik1": "TIK-001", "tik2": "TIK-002", "tik3": "TIK-003"}


# --- Authentication & Security Tests ---

def test_unauthenticated_requests_rejected() -> None:
    """Verifies that unauthenticated requests to protected endpoints return HTTP 401 (P2-EV-002, P2-EC-001)."""
    # 1. No Authorization header
    resp = client.get("/api/v1/tickets")
    assert resp.status_code == 401
    err = resp.json()["error"]
    assert err["code"] == "UNAUTHORIZED"

    resp = client.get("/api/v1/tickets/TIK-001")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"

    resp = client.get("/api/v1/tickets/TIK-001/context")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"

    # 2. Invalid token
    resp = client.get("/api/v1/tickets", headers={"Authorization": "Bearer wrong_token"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_security_headers_present() -> None:
    """Verifies that security headers are attached to responses (docs/architecture.md §5.2)."""
    resp = client.get("/api/v1/tickets", headers=AUTH_HEADER)
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Content-Security-Policy"] == "default-src 'self'"


# --- Ticket Listing & Filtering Tests ---

def test_list_tickets_authenticated() -> None:
    """Verifies listing tickets with total count and pagination structure (P2-EV-006)."""
    _seed_test_data()
    resp = client.get("/api/v1/tickets", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    assert data["limit"] == 50
    assert data["offset"] == 0

    # Verify summary fields
    first = data["items"][0]
    assert "ticket_id" in first
    assert "customer_id" in first
    assert "subject" in first
    assert "status" in first
    assert "created_at" in first


def test_list_tickets_status_filter() -> None:
    """Verifies filtering tickets by operational status (P2-EV-007)."""
    _seed_test_data()
    resp = client.get("/api/v1/tickets?status=open", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert all(item["status"] == "open" for item in data["items"])

    resp_closed = client.get("/api/v1/tickets?status=closed", headers=AUTH_HEADER)
    assert resp_closed.status_code == 200
    data_closed = resp_closed.json()
    assert data_closed["total"] == 1
    assert data_closed["items"][0]["status"] == "closed"


def test_list_tickets_customer_filter() -> None:
    """Verifies filtering tickets by customer_id (P2-EV-008)."""
    _seed_test_data()
    resp = client.get("/api/v1/tickets?customer_id=CUST-001", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert all(item["customer_id"] == "CUST-001" for item in data["items"])


def test_list_tickets_empty_result() -> None:
    """Verifies filtering with no matches returns 200 OK with empty list (P2-EC-005)."""
    _seed_test_data()
    resp = client.get("/api/v1/tickets?customer_id=CUST-NONEXISTENT", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_list_tickets_pagination_slicing() -> None:
    """Verifies limit and offset slicing behavior (P2-EV-009)."""
    _seed_test_data()
    # Page 1
    resp1 = client.get("/api/v1/tickets?limit=2&offset=0", headers=AUTH_HEADER)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert len(data1["items"]) == 2
    assert data1["total"] == 3

    # Page 2
    resp2 = client.get("/api/v1/tickets?limit=2&offset=2", headers=AUTH_HEADER)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert len(data2["items"]) == 1
    assert data2["total"] == 3

    # Disjoint check
    page1_ids = {item["ticket_id"] for item in data1["items"]}
    page2_ids = {item["ticket_id"] for item in data2["items"]}
    assert page1_ids.isdisjoint(page2_ids)


def test_list_tickets_invalid_pagination_returns_422() -> None:
    """Verifies invalid pagination parameters trigger HTTP 422 with validation error envelope (P2-EC-006)."""
    resp_zero = client.get("/api/v1/tickets?limit=0", headers=AUTH_HEADER)
    assert resp_zero.status_code == 422
    err_zero = resp_zero.json()["error"]
    assert err_zero["code"] == "VALIDATION_ERROR"
    assert "errors" in err_zero["details"]

    resp_neg = client.get("/api/v1/tickets?offset=-1", headers=AUTH_HEADER)
    assert resp_neg.status_code == 422
    err_neg = resp_neg.json()["error"]
    assert err_neg["code"] == "VALIDATION_ERROR"


# --- Single Ticket Detail Tests ---

def test_get_ticket_detail_success() -> None:
    """Verifies single ticket detail retrieval matches stored fields (P2-EV-010)."""
    _seed_test_data()
    resp = client.get("/api/v1/tickets/TIK-001", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticket_id"] == "TIK-001"
    assert data["customer_id"] == "CUST-001"
    assert data["order_id"] == "ORD-001"
    assert data["subject"] == "Headphones arrived defective"
    assert data["message"] == "Right earbud has no audio."
    assert data["status"] == "open"
    assert data["raw_metadata"]["priority"] == "high"


def test_get_ticket_detail_not_found() -> None:
    """Verifies non-existent ticket ID returns HTTP 404 (P2-EV-013, P2-EC-003)."""
    resp = client.get("/api/v1/tickets/TIK-NONEXISTENT", headers=AUTH_HEADER)
    assert resp.status_code == 404
    err = resp.json()["error"]
    assert err["code"] == "TICKET_NOT_FOUND"
    assert "TIK-NONEXISTENT" in err["message"]
    assert err["details"]["ticket_id"] == "TIK-NONEXISTENT"


# --- Ticket Context Retrieval Tests ---

def test_get_ticket_context_full() -> None:
    """Verifies context assembly for ticket with linked order and customer past tickets (P2-EV-011)."""
    _seed_test_data()
    resp = client.get("/api/v1/tickets/TIK-001/context", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()

    # Ticket detail
    assert data["ticket"]["ticket_id"] == "TIK-001"

    # Customer profile
    customer = data["customer"]
    assert customer["customer_id"] == "CUST-001"
    assert customer["name"] == "Alice Walker"
    assert customer["email"] == "alice@example.com"
    assert customer["metadata"]["vip"] is True

    # Linked order
    order = data["order"]
    assert order is not None
    assert order["order_id"] == "ORD-001"
    assert order["status"] == "delivered"
    assert Decimal(str(order["total_amount"])) == Decimal("150.00")
    assert len(order["items"]) == 1
    assert order["items"][0]["sku"] == "SKU-A"

    # Past tickets for this customer (excluding active ticket TIK-001)
    past = data["past_tickets"]
    assert len(past) == 1
    assert past[0]["ticket_id"] == "TIK-002"
    assert all(t["ticket_id"] != "TIK-001" for t in past)


def test_get_ticket_context_unlinked_order_is_null() -> None:
    """Verifies context assembly for ticket with order_id = NULL returns order = null (P2-EV-012, P2-EC-002)."""
    _seed_test_data()
    resp = client.get("/api/v1/tickets/TIK-002/context", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()

    assert data["ticket"]["ticket_id"] == "TIK-002"
    assert data["customer"]["customer_id"] == "CUST-001"
    assert data["order"] is None
    # Past tickets for Cust 1 should contain TIK-001
    past = data["past_tickets"]
    assert len(past) == 1
    assert past[0]["ticket_id"] == "TIK-001"


def test_get_ticket_context_quarantined_reference() -> None:
    """Verifies ticket context preserves quarantined order reference in raw_metadata (P2-EC-007)."""
    _seed_test_data()
    resp = client.get("/api/v1/tickets/TIK-003/context", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()

    assert data["ticket"]["ticket_id"] == "TIK-003"
    assert data["ticket"]["order_id"] is None
    assert data["ticket"]["raw_metadata"]["unresolved_order_id"] == "ORD-MISSING-999"
    assert data["order"] is None


def test_get_ticket_context_customer_single_ticket_history_is_empty() -> None:
    """Verifies customer with single ticket returns empty past_tickets list (P2-EC-008)."""
    _seed_test_data()
    # Cust 2 has only TIK-003
    resp = client.get("/api/v1/tickets/TIK-003/context", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["past_tickets"] == []


def test_get_ticket_context_not_found() -> None:
    """Verifies context request for non-existent ticket returns 404 (P2-EV-013, P2-EC-003)."""
    resp = client.get("/api/v1/tickets/TIK-MISSING-999/context", headers=AUTH_HEADER)
    assert resp.status_code == 404
    err = resp.json()["error"]
    assert err["code"] == "TICKET_NOT_FOUND"


# --- Database Connection Failure Resilience ---

def test_ticket_api_database_disconnected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies ticket APIs return HTTP 503 when the database connection drops (P2-EC-010)."""
    def mock_broken_db():
        broken_engine = create_engine(
            "postgresql+psycopg://invalid:invalid@127.0.0.1:54999/down",
            connect_args={"connect_timeout": 1},
        )
        BrokenSession = sessionmaker(bind=broken_engine)
        session = BrokenSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = mock_broken_db
    try:
        resp = client.get("/api/v1/tickets", headers=AUTH_HEADER)
        assert resp.status_code == 503
        err = resp.json()["error"]
        assert err["code"] == "DATABASE_UNAVAILABLE"
    finally:
        app.dependency_overrides.clear()

