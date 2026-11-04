from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from trustdesk.core.exceptions import IngestionError
from trustdesk.core.logging import get_logger
from trustdesk.models.customer import Customer
from trustdesk.models.knowledge import KnowledgeDocument
from trustdesk.models.order import Order
from trustdesk.models.quarantine import QuarantinedRecord
from trustdesk.models.ticket import Ticket
from trustdesk.services.knowledge_service import derive_and_index_sections
from trustdesk.tools.catalog import registry as tool_registry

logger = get_logger(__name__)


def parse_timestamp(value: Any) -> datetime:
    """Parses ISO 8601 timestamp string preserving timezone offset."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise ValueError(f"Expected ISO 8601 string or datetime, got {type(value).__name__}: {value}")


def ingest_customers(session: Session, file_path: Path) -> int:
    """Ingests customers from JSON file using upsert idempotency."""
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            records = json.load(f)
        except json.JSONDecodeError as exc:
            raise IngestionError(f"Malformed JSON in {file_path.name}: {exc}") from exc

    if not isinstance(records, list):
        raise IngestionError(f"File {file_path.name} must contain a JSON array of objects.")

    dialect_name = session.bind.dialect.name if session.bind else "postgresql"
    count = 0

    for item in records:
        customer_id = item["customer_id"]
        email = item.get("email")
        name = item.get("name")
        metadata_json = item.get("metadata", {})
        created_at = parse_timestamp(item.get("created_at", datetime.now()))

        if dialect_name == "postgresql":
            insert_stmt = pg_insert(Customer).values(
                customer_id=customer_id,
                email=email,
                name=name,
                metadata_json=metadata_json,
                created_at=created_at,
            )
            stmt = insert_stmt.on_conflict_do_update(
                index_elements=["customer_id"],
                set_={
                    "email": insert_stmt.excluded.email,
                    "name": insert_stmt.excluded.name,
                    "metadata": insert_stmt.excluded["metadata"],
                },
            )
            session.execute(stmt)
        else:
            # Fallback for SQLite / generic dialects
            existing = session.get(Customer, customer_id)
            if existing:
                existing.email = email
                existing.name = name
                existing.metadata_json = metadata_json
            else:
                session.add(
                    Customer(
                        customer_id=customer_id,
                        email=email,
                        name=name,
                        metadata_json=metadata_json,
                        created_at=created_at,
                    )
                )
        count += 1

    session.flush()
    logger.info("Ingested %d customers from %s", count, file_path.name)
    return count


def ingest_orders(session: Session, file_path: Path) -> int:
    """Ingests orders from JSON file using upsert idempotency."""
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            records = json.load(f)
        except json.JSONDecodeError as exc:
            raise IngestionError(f"Malformed JSON in {file_path.name}: {exc}") from exc

    if not isinstance(records, list):
        raise IngestionError(f"File {file_path.name} must contain a JSON array of objects.")

    dialect_name = session.bind.dialect.name if session.bind else "postgresql"
    count = 0

    for item in records:
        order_id = item["order_id"]
        customer_id = item["customer_id"]
        order_date = parse_timestamp(item["order_date"])
        delivery_date = parse_timestamp(item["delivery_date"]) if item.get("delivery_date") else None
        status = item.get("status")
        total_amount = item.get("total_amount")
        items = item.get("items", [])

        if dialect_name == "postgresql":
            insert_stmt = pg_insert(Order).values(
                order_id=order_id,
                customer_id=customer_id,
                order_date=order_date,
                delivery_date=delivery_date,
                status=status,
                total_amount=total_amount,
                items=items,
            )
            stmt = insert_stmt.on_conflict_do_update(
                index_elements=["order_id"],
                set_={
                    "customer_id": insert_stmt.excluded.customer_id,
                    "order_date": insert_stmt.excluded.order_date,
                    "delivery_date": insert_stmt.excluded.delivery_date,
                    "status": insert_stmt.excluded.status,
                    "total_amount": insert_stmt.excluded.total_amount,
                    "items": insert_stmt.excluded["items"],
                },
            )
            session.execute(stmt)
        else:
            existing = session.get(Order, order_id)
            if existing:
                existing.customer_id = customer_id
                existing.order_date = order_date
                existing.delivery_date = delivery_date
                existing.status = status
                existing.total_amount = total_amount
                existing.items = items
            else:
                session.add(
                    Order(
                        order_id=order_id,
                        customer_id=customer_id,
                        order_date=order_date,
                        delivery_date=delivery_date,
                        status=status,
                        total_amount=total_amount,
                        items=items,
                    )
                )
        count += 1

    session.flush()
    logger.info("Ingested %d orders from %s", count, file_path.name)
    return count


def ingest_tickets(session: Session, file_path: Path) -> int:
    """Ingests tickets with strict foreign-key handling and quarantine policy.

    Rules:
    1. Mandatory parent missing: If customer_id does not exist in customers table,
       the ticket is quarantined in `quarantined_records` (P1-EC-004, P1-EV-008).
    2. Naturally absent order_id (null or empty string): order_id is stored as NULL cleanly (P1-EC-002, P1-EV-006).
    3. Invalid non-null order_id: If order_id is not present in orders table, store order_id = NULL
       and preserve raw string in raw_metadata["unresolved_order_id"] (P1-EC-003, P1-EV-007).
    """
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            records = json.load(f)
        except json.JSONDecodeError as exc:
            raise IngestionError(f"Malformed JSON in {file_path.name}: {exc}") from exc

    if not isinstance(records, list):
        raise IngestionError(f"File {file_path.name} must contain a JSON array of objects.")

    dialect_name = session.bind.dialect.name if session.bind else "postgresql"
    count = 0

    for item in records:
        ticket_id = item["ticket_id"]
        customer_id = item["customer_id"]
        raw_order_id = item.get("order_id")
        subject = item["subject"]
        message = item["message"]
        status = item.get("status", "open")
        created_at = parse_timestamp(item["created_at"])
        raw_metadata: dict[str, Any] = dict(item.get("raw_metadata") or {})

        # 1. Mandatory parent check (P1-EC-004)
        customer_exists = session.get(Customer, customer_id) is not None
        if not customer_exists:
            logger.error(
                "Quarantining ticket '%s': mandatory customer_id '%s' does not exist.",
                ticket_id,
                customer_id,
            )
            quarantine_record = QuarantinedRecord(
                record_type="ticket",
                record_id=ticket_id,
                reason=f"Mandatory parent customer_id '{customer_id}' not found",
                raw_payload=item,
            )
            session.add(quarantine_record)
            continue

        # 2. Relational Order ID validation & Quarantine Policy (P1-EC-002, P1-EC-003)
        effective_order_id: str | None = None
        if raw_order_id:
            order_exists = session.get(Order, raw_order_id) is not None
            if order_exists:
                effective_order_id = raw_order_id
            else:
                # Invalid non-null foreign key: preserve raw string in metadata, set relational column to NULL
                logger.warning(
                    "Ticket '%s' references unresolvable order_id '%s'. Quarantining reference in raw_metadata.",
                    ticket_id,
                    raw_order_id,
                )
                effective_order_id = None
                raw_metadata["unresolved_order_id"] = raw_order_id
        else:
            # Naturally absent order reference
            effective_order_id = None

        if dialect_name == "postgresql":
            insert_stmt = pg_insert(Ticket).values(
                ticket_id=ticket_id,
                customer_id=customer_id,
                order_id=effective_order_id,
                subject=subject,
                message=message,
                status=status,
                created_at=created_at,
                raw_metadata=raw_metadata,
            )
            stmt = insert_stmt.on_conflict_do_update(
                index_elements=["ticket_id"],
                set_={
                    "customer_id": insert_stmt.excluded.customer_id,
                    "order_id": insert_stmt.excluded.order_id,
                    "subject": insert_stmt.excluded.subject,
                    "message": insert_stmt.excluded.message,
                    "status": insert_stmt.excluded.status,
                    "created_at": insert_stmt.excluded.created_at,
                    "raw_metadata": insert_stmt.excluded["raw_metadata"],
                },
            )
            session.execute(stmt)
        else:
            existing = session.get(Ticket, ticket_id)
            if existing:
                existing.customer_id = customer_id
                existing.order_id = effective_order_id
                existing.subject = subject
                existing.message = message
                existing.status = status
                existing.created_at = created_at
                existing.raw_metadata = raw_metadata
            else:
                session.add(
                    Ticket(
                        ticket_id=ticket_id,
                        customer_id=customer_id,
                        order_id=effective_order_id,
                        subject=subject,
                        message=message,
                        status=status,
                        created_at=created_at,
                        raw_metadata=raw_metadata,
                    )
                )
        count += 1

    session.flush()
    logger.info("Ingested %d valid tickets from %s", count, file_path.name)
    return count


def ingest_kb_documents(session: Session, file_path: Path) -> int:
    """Ingests raw knowledge-base documents verbatim, preserving original alphanumeric identifiers."""
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            records = json.load(f)
        except json.JSONDecodeError as exc:
            raise IngestionError(f"Malformed JSON in {file_path.name}: {exc}") from exc

    if not isinstance(records, list):
        raise IngestionError(f"File {file_path.name} must contain a JSON array of objects.")

    dialect_name = session.bind.dialect.name if session.bind else "postgresql"
    count = 0

    for item in records:
        kb_id = item["kb_id"]
        title = item["title"]
        category = item["category"]
        raw_content = item["raw_content"]

        if dialect_name == "postgresql":
            insert_stmt = pg_insert(KnowledgeDocument).values(
                kb_id=kb_id,
                title=title,
                category=category,
                raw_content=raw_content,
            )
            stmt = insert_stmt.on_conflict_do_update(
                index_elements=["kb_id"],
                set_={
                    "title": insert_stmt.excluded.title,
                    "category": insert_stmt.excluded.category,
                    "raw_content": insert_stmt.excluded.raw_content,
                },
            )
            session.execute(stmt)
        else:
            existing = session.get(KnowledgeDocument, kb_id)
            if existing:
                existing.title = title
                existing.category = category
                existing.raw_content = raw_content
            else:
                session.add(
                    KnowledgeDocument(
                        kb_id=kb_id,
                        title=title,
                        category=category,
                        raw_content=raw_content,
                    )
                )
        count += 1

    session.flush()
    logger.info("Ingested %d knowledge documents from %s", count, file_path.name)
    return count


def ingest_dataset(session: Session, data_dir: Path | str = "./data") -> dict[str, int]:
    """Coordinates full dataset ingestion across all domain entities with transaction management."""
    path = Path(data_dir)
    if not path.exists() or not path.is_dir():
        raise IngestionError(f"Source data directory does not exist or is not a directory: {path}")

    required_files = {
        "customers": path / "customers.json",
        "orders": path / "orders.json",
        "tickets": path / "tickets.json",
        "kb_documents": path / "kb_documents.json",
    }

    missing_files = [str(p.name) for p in required_files.values() if not p.is_file()]
    if missing_files:
        raise IngestionError(f"Missing required source dataset file(s) in {path}: {', '.join(missing_files)}")

    # Ingest Tool Catalog into in-memory registry (P1-EC-007, U-013)
    tool_catalog_path = path / "tool_catalog.json"
    tool_count = 0
    if tool_catalog_path.is_file():
        registered_tools = tool_registry.load_from_file(tool_catalog_path)
        tool_count = len(registered_tools)

    # Ingest entities in dependency order within transaction
    try:
        customers_count = ingest_customers(session, required_files["customers"])
        orders_count = ingest_orders(session, required_files["orders"])
        tickets_count = ingest_tickets(session, required_files["tickets"])
        kb_count = ingest_kb_documents(session, required_files["kb_documents"])
        kb_sections_count = derive_and_index_sections(session)
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("Dataset ingestion failed. Transaction rolled back cleanly: %s", exc)
        raise

    summary = {
        "customers": customers_count,
        "orders": orders_count,
        "tickets": tickets_count,
        "kb_documents": kb_count,
        "kb_sections": kb_sections_count,
        "tools": tool_count,
    }
    logger.info("Ingestion completed successfully: %s", summary)
    return summary

