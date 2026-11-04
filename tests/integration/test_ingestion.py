from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select, func, text

from trustdesk.core.database import Base, engine, get_db_session
from trustdesk.core.exceptions import IngestionError
from trustdesk.models.customer import Customer
from trustdesk.models.knowledge import KBSection, KnowledgeDocument
from trustdesk.models.order import Order
from trustdesk.models.quarantine import QuarantinedRecord
from trustdesk.models.ticket import Ticket
from trustdesk.services.ingestion import ingest_dataset, ingest_tickets, ingest_customers
from trustdesk.tools.catalog import registry as tool_registry


@pytest.fixture(autouse=True)
def setup_database_schema():
    """Ensure database schema is created and fresh for integration tests."""
    Base.metadata.create_all(bind=engine)
    with get_db_session() as session:
        session.execute(text("TRUNCATE TABLE quarantined_records, tickets, orders, customers, kb_documents CASCADE;"))
        session.commit()
    yield


def test_source_dataset_ingestion_pipeline() -> None:
    """Verifies end-to-end dataset ingestion from ./data (P1-EV-003, P1-EC-001)."""
    with get_db_session() as session:
        summary = ingest_dataset(session=session, data_dir="./data")

        assert summary["customers"] >= 5
        assert summary["orders"] >= 4
        assert summary["tickets"] >= 4
        assert summary["kb_documents"] >= 4
        assert summary["tools"] >= 5

        # Query database row counts
        cust_count = session.scalar(select(func.count()).select_from(Customer))
        order_count = session.scalar(select(func.count()).select_from(Order))
        ticket_count = session.scalar(select(func.count()).select_from(Ticket))
        kb_count = session.scalar(select(func.count()).select_from(KnowledgeDocument))

        assert cust_count == summary["customers"]
        assert order_count == summary["orders"]
        assert ticket_count == summary["tickets"]
        assert kb_count == summary["kb_documents"]


def test_ingestion_idempotency_and_repeatability() -> None:
    """Verifies consecutive ingestion executions produce identical row counts (P1-EV-004, P1-EC-001)."""
    with get_db_session() as session:
        # Run 1
        summary_1 = ingest_dataset(session=session, data_dir="./data")
        cust_count_1 = session.scalar(select(func.count()).select_from(Customer))
        order_count_1 = session.scalar(select(func.count()).select_from(Order))
        ticket_count_1 = session.scalar(select(func.count()).select_from(Ticket))
        kb_count_1 = session.scalar(select(func.count()).select_from(KnowledgeDocument))

        # Run 2
        summary_2 = ingest_dataset(session=session, data_dir="./data")
        cust_count_2 = session.scalar(select(func.count()).select_from(Customer))
        order_count_2 = session.scalar(select(func.count()).select_from(Order))
        ticket_count_2 = session.scalar(select(func.count()).select_from(Ticket))
        kb_count_2 = session.scalar(select(func.count()).select_from(KnowledgeDocument))

        assert cust_count_1 == cust_count_2
        assert order_count_1 == order_count_2
        assert ticket_count_1 == ticket_count_2
        assert kb_count_1 == kb_count_2


def test_identifier_preservation_for_kb_documents() -> None:
    """Verifies verbatim preservation of original KB document IDs including adversarial (P1-EV-005, P1-EC-005, P1-EC-006)."""
    with get_db_session() as session:
        ingest_dataset(session=session, data_dir="./data")

        refund_doc = session.get(KnowledgeDocument, "KB-REFUND-001")
        assert refund_doc is not None
        assert refund_doc.kb_id == "KB-REFUND-001"
        assert refund_doc.category == "refund"
        assert "30 calendar days" in refund_doc.raw_content

        adv_doc = session.get(KnowledgeDocument, "KB-ADVERSARIAL-001")
        assert adv_doc is not None
        assert adv_doc.kb_id == "KB-ADVERSARIAL-001"
        assert "IGNORE ALL PREVIOUS INSTRUCTIONS" in adv_doc.raw_content


def test_naturally_null_foreign_key_handling() -> None:
    """Verifies that tickets with null order references persist cleanly with order_id = NULL (P1-EV-006, P1-EC-002)."""
    with get_db_session() as session:
        ingest_dataset(session=session, data_dir="./data")

        ticket = session.get(Ticket, "TIK-NO-ORDER")
        assert ticket is not None
        assert ticket.order_id is None
        assert ticket.customer_id == "CUST-004"


def test_invalid_non_null_foreign_key_quarantine_policy(tmp_path: Path) -> None:
    """Verifies that an unresolvable order_id sets order_id=NULL and quarantines raw string in raw_metadata (P1-EV-007, P1-EC-003)."""
    with get_db_session() as session:
        ingest_dataset(session=session, data_dir="./data")

        # Create temporary fixture ticket referencing non-existent order
        fixture_ticket = [
            {
                "ticket_id": "TIK-TEST-INVALID-ORD",
                "customer_id": "CUST-001",
                "order_id": "ORD-MISSING-9999",
                "subject": "Missing order reference test",
                "message": "My order reference does not exist in the database.",
                "status": "open",
                "created_at": "2026-11-01T10:00:00Z",
            }
        ]
        ticket_file = tmp_path / "test_tickets.json"
        ticket_file.write_text(json.dumps(fixture_ticket), encoding="utf-8")

        ingest_tickets(session=session, file_path=ticket_file)
        session.commit()

        persisted = session.get(Ticket, "TIK-TEST-INVALID-ORD")
        assert persisted is not None
        assert persisted.order_id is None
        assert persisted.raw_metadata.get("unresolved_order_id") == "ORD-MISSING-9999"


def test_mandatory_parent_customer_reference_validation(tmp_path: Path) -> None:
    """Verifies that a ticket referencing a non-existent customer is quarantined, not inserted into tickets (P1-EV-008, P1-EC-004)."""
    with get_db_session() as session:
        ingest_dataset(session=session, data_dir="./data")

        fixture_orphaned = [
            {
                "ticket_id": "TIK-ORPHAN-001",
                "customer_id": "CUST-NONEXISTENT-999",
                "order_id": None,
                "subject": "Orphaned ticket test",
                "message": "Customer does not exist in database.",
                "status": "open",
                "created_at": "2026-11-01T10:00:00Z",
            }
        ]
        ticket_file = tmp_path / "orphaned_tickets.json"
        ticket_file.write_text(json.dumps(fixture_orphaned), encoding="utf-8")

        ingest_tickets(session=session, file_path=ticket_file)
        session.commit()

        # Ticket must not exist in tickets table
        ticket = session.get(Ticket, "TIK-ORPHAN-001")
        assert ticket is None

        # Record must be present in quarantined_records
        quarantine_stmt = select(QuarantinedRecord).where(QuarantinedRecord.record_id == "TIK-ORPHAN-001")
        quarantined = session.scalar(quarantine_stmt)
        assert quarantined is not None
        assert quarantined.record_type == "ticket"
        assert "CUST-NONEXISTENT-999" in quarantined.reason


def test_tool_catalog_scope_enforcement() -> None:
    """Verifies tool catalog restricts active operational tools to start_refund_review (P1-EV-009, P1-EC-007)."""
    tool_registry.clear()
    tools = tool_registry.load_from_file("./data/tool_catalog.json")

    assert len(tools) >= 5

    # start_refund_review is supported
    refund_tool = tool_registry.get("start_refund_review")
    assert refund_tool is not None
    assert refund_tool.is_supported is True
    assert refund_tool.is_sensitive is True
    assert refund_tool.in_scope is True

    # create_replacement_order is flagged unsupported and out of scope
    replacement_tool = tool_registry.get("create_replacement_order")
    assert replacement_tool is not None
    assert replacement_tool.is_supported is False
    assert replacement_tool.in_scope is False

    # issue_direct_refund is flagged unsupported and out of scope
    direct_refund_tool = tool_registry.get("issue_direct_refund")
    assert direct_refund_tool is not None
    assert direct_refund_tool.is_supported is False
    assert direct_refund_tool.in_scope is False

    # Strictly only start_refund_review is active operational tool
    active_operational = tool_registry.get_active_operational_tools()
    assert len(active_operational) == 1
    assert active_operational[0].name == "start_refund_review"


def test_ingestion_corrupted_json_handling(tmp_path: Path) -> None:
    """Verifies transaction rollback and IngestionError on malformed JSON (P1-EV-012, P1-EC-010)."""
    corrupt_dir = tmp_path / "corrupt_data"
    corrupt_dir.mkdir()

    # Create malformed customers.json
    (corrupt_dir / "customers.json").write_text('[{"customer_id": "CUST-BAD", "email": "bad@example.com",}]', encoding="utf-8")
    (corrupt_dir / "orders.json").write_text("[]", encoding="utf-8")
    (corrupt_dir / "tickets.json").write_text("[]", encoding="utf-8")
    (corrupt_dir / "kb_documents.json").write_text("[]", encoding="utf-8")

    with get_db_session() as session:
        with pytest.raises(IngestionError) as exc_info:
            ingest_dataset(session=session, data_dir=corrupt_dir)
        assert "Malformed JSON" in str(exc_info.value)


def test_ingestion_missing_directory_handling(tmp_path: Path) -> None:
    """Verifies IngestionError when directory or required files are missing (P1-EV-013, P1-EC-009)."""
    non_existent = tmp_path / "non_existent_dir"
    with get_db_session() as session:
        with pytest.raises(IngestionError) as exc_info:
            ingest_dataset(session=session, data_dir=non_existent)
        assert "does not exist" in str(exc_info.value)

    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    with get_db_session() as session:
        with pytest.raises(IngestionError) as exc_info:
            ingest_dataset(session=session, data_dir=empty_dir)
        assert "Missing required source dataset file" in str(exc_info.value)


def test_timezone_normalization_and_preservation() -> None:
    """Verifies accurate UTC storage and timedelta calculations on offset timestamps (P1-EV-014, P1-EC-011)."""
    with get_db_session() as session:
        ingest_dataset(session=session, data_dir="./data")

        # ORD-001: 2026-10-15T14:30:00-04:00 (UTC 18:30:00)
        # TIK-001: 2026-11-01T09:00:00+02:00 (UTC 07:00:00)
        order = session.get(Order, "ORD-001")
        ticket = session.get(Ticket, "TIK-001")

        assert order is not None
        assert ticket is not None

        # Time difference calculation (Authoritative temporal policy evaluation)
        delta = ticket.created_at - order.order_date
        assert delta.days >= 16


def test_primary_key_conflict_with_updated_source_attributes(tmp_path: Path) -> None:
    """Verifies in-place update on primary key conflict without duplicate rows (P1-EV-015, P1-EC-012)."""
    with get_db_session() as session:
        ingest_dataset(session=session, data_dir="./data")

        # Initial email
        initial_cust = session.get(Customer, "CUST-001")
        assert initial_cust is not None
        assert initial_cust.email == "sarah.connor@example.com"

        # Refreshed dataset fixture with modified email
        updated_data = [
            {
                "customer_id": "CUST-001",
                "email": "sarah.updated@example.com",
                "name": "Sarah Connor Updated",
                "metadata": {"membership": "platinum"},
                "created_at": "2025-03-15T08:00:00Z",
            }
        ]
        update_file = tmp_path / "updated_customers.json"
        update_file.write_text(json.dumps(updated_data), encoding="utf-8")

        ingest_customers(session=session, file_path=update_file)
        session.commit()
        session.expire_all()

        # Check updated record
        refreshed_cust = session.get(Customer, "CUST-001")
        assert refreshed_cust is not None
        assert refreshed_cust.email == "sarah.updated@example.com"
        assert refreshed_cust.name == "Sarah Connor Updated"

        # Verify row count is unchanged
        total_customers = session.scalar(select(func.count()).select_from(Customer).where(Customer.customer_id == "CUST-001"))
        assert total_customers == 1


def test_ingest_dataset_derives_kb_sections() -> None:
    """Verifies that ingest_dataset automatically derives and persists kb_sections (P3-EV-012)."""
    with get_db_session() as session:
        summary = ingest_dataset(session=session, data_dir="./data")
        assert "kb_sections" in summary
        assert summary["kb_sections"] == 9

        # Confirm in database
        section_count = session.scalar(select(func.count()).select_from(KBSection))
        assert section_count == 9


