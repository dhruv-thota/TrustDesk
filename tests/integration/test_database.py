from __future__ import annotations

import pytest
from sqlalchemy import inspect, text

from trustdesk.core.database import Base, check_database_connection, engine, get_db_session


def test_database_connection_ping() -> None:
    """Verifies that the database engine can execute a SELECT 1 ping (P1-EV-002)."""
    with get_db_session() as session:
        result = check_database_connection(custom_session=session)
        assert result == {"status": "healthy", "database": "connected"}


def test_schema_tables_exist() -> None:
    """Verifies that all Phase 1 source tables are defined in metadata and exist in schema (P1-EV-002)."""
    # Ensure tables are created on the connected database
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    required_tables = {"customers", "orders", "tickets", "kb_documents", "quarantined_records"}
    for table in required_tables:
        assert table in existing_tables, f"Table '{table}' missing from database schema"

    # Verify primary keys
    assert inspector.get_pk_constraint("customers")["constrained_columns"] == ["customer_id"]
    assert inspector.get_pk_constraint("orders")["constrained_columns"] == ["order_id"]
    assert inspector.get_pk_constraint("tickets")["constrained_columns"] == ["ticket_id"]
    assert inspector.get_pk_constraint("kb_documents")["constrained_columns"] == ["kb_id"]

