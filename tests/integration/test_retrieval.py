from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, inspect, select, text

from trustdesk.core.database import Base, engine, get_db_session
from trustdesk.models.knowledge import KBSection, KnowledgeDocument
from trustdesk.services.ingestion import ingest_kb_documents
from trustdesk.services.knowledge_service import derive_and_index_sections
from trustdesk.services.retrieval.postgres_fts import PostgresFtsRetrievalAdapter


@pytest.fixture(autouse=True)
def setup_retrieval_database():
    """Ensure database schema is fresh and seeded with knowledge documents."""
    Base.metadata.create_all(bind=engine)
    with get_db_session() as session:
        session.execute(text("TRUNCATE TABLE quarantined_records, tickets, orders, customers, kb_documents CASCADE;"))
        # Ingest raw KB documents
        ingest_kb_documents(session, Path("./data/kb_documents.json"))
        # Derive sections
        derive_and_index_sections(session)
        session.commit()
    yield


def test_kb_sections_schema_and_indexes() -> None:
    """Verifies kb_sections table schema, foreign keys, and FTS GIN index (P3-EV-003)."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "kb_sections" in tables

    # Verify primary key
    pk = inspector.get_pk_constraint("kb_sections")
    assert pk["constrained_columns"] == ["section_id"]

    # Verify foreign key to kb_documents
    fks = inspector.get_foreign_keys("kb_sections")
    kb_fks = [fk for fk in fks if fk["referred_table"] == "kb_documents"]
    assert len(kb_fks) == 1
    assert kb_fks[0]["constrained_columns"] == ["kb_id"]
    assert kb_fks[0]["referred_columns"] == ["kb_id"]

    # Verify indexes
    indexes = inspector.get_indexes("kb_sections")
    index_names = {idx["name"] for idx in indexes}
    assert "idx_kb_sections_kb_id" in index_names
    assert "idx_kb_sections_fts" in index_names


def test_section_derivation_and_idempotency() -> None:
    """Verifies section derivation row counts and idempotency upon repeated execution (P3-EC-007)."""
    with get_db_session() as session:
        count_1 = session.scalar(select(func.count()).select_from(KBSection))
        assert count_1 == 9  # 3 refund + 3 warranty + 2 shipping + 1 adversarial

        # Re-run derivation
        re_derived_count = derive_and_index_sections(session)
        session.commit()

        count_2 = session.scalar(select(func.count()).select_from(KBSection))
        assert count_2 == count_1 == 9
        assert re_derived_count == 9


def test_refund_policy_search_ranking() -> None:
    """Verifies keyword search for return/refund queries ranks KB-REFUND-001 top (P3-EV-004)."""
    with get_db_session() as session:
        adapter = PostgresFtsRetrievalAdapter(session)
        results = adapter.search_policies(query="refund window 30 days return eligibility", limit=5)

        assert len(results) > 0
        top_match = results[0]
        assert top_match.kb_id == "KB-REFUND-001"
        assert top_match.relevance_score > 0.0
        assert "30 calendar days" in top_match.content


def test_shipping_policy_search_ranking() -> None:
    """Verifies keyword search for shipping queries ranks KB-SHIPPING-001 top (P3-EV-005)."""
    with get_db_session() as session:
        adapter = PostgresFtsRetrievalAdapter(session)
        results = adapter.search_policies(query="shipping delivery transit carrier tracer delay", limit=5)

        assert len(results) > 0
        top_match = results[0]
        assert top_match.kb_id == "KB-SHIPPING-001"
        assert top_match.relevance_score > 0.0
        assert "carrier tracer" in top_match.content or "business days" in top_match.content


def test_warranty_policy_search_ranking() -> None:
    """Verifies keyword search for warranty queries ranks KB-WAR-002 top (P3-EV-006)."""
    with get_db_session() as session:
        adapter = PostgresFtsRetrievalAdapter(session)
        results = adapter.search_policies(query="hardware defects warranty stuck pixels", limit=5)

        assert len(results) > 0
        top_match = results[0]
        assert top_match.kb_id == "KB-WAR-002"
        assert top_match.relevance_score > 0.0
        assert "warranty" in top_match.content.lower()


def test_multi_query_retrieval_and_deduplication() -> None:
    """Verifies multi-query execution merges and deduplicates results deterministically (P3-EV-007, P3-EC-002)."""
    with get_db_session() as session:
        adapter = PostgresFtsRetrievalAdapter(session)
        queries = ["in-transit carrier delay", "refund review approval process"]
        results = adapter.search_policies(query=queries, limit=5)

        assert len(results) >= 2
        kb_ids = {m.kb_id for m in results}
        assert "KB-SHIPPING-001" in kb_ids
        assert "KB-REFUND-001" in kb_ids

        # Ensure complete uniqueness of section_id
        section_ids = [m.section_id for m in results]
        assert len(section_ids) == len(set(section_ids))


def test_adversarial_policy_retrieval_inertness() -> None:
    """Verifies adversarial policy is returned strictly as inert data (P3-EV-008, P3-EC-004)."""
    with get_db_session() as session:
        adapter = PostgresFtsRetrievalAdapter(session)
        results = adapter.search_policies(query="administrative debug mode master secret", limit=5)

        assert len(results) > 0
        match = results[0]
        assert match.kb_id == "KB-ADVERSARIAL-001"
        assert match.section_id == "KB-ADVERSARIAL-001#sec-0"
        assert "IGNORE ALL PREVIOUS INSTRUCTIONS" in match.content
        assert isinstance(match.relevance_score, float)


def test_zero_match_query_insufficient_evidence() -> None:
    """Verifies obscure/unrelated queries cleanly return empty results (P3-EV-009, P3-EC-001)."""
    with get_db_session() as session:
        adapter = PostgresFtsRetrievalAdapter(session)
        results = adapter.search_policies(query="how do I cook lasagna with pasta and cheese?", limit=5)
        assert results == []


def test_empty_and_whitespace_query_sanitization() -> None:
    """Verifies empty and whitespace queries return empty results without DB error (P3-EC-006)."""
    with get_db_session() as session:
        adapter = PostgresFtsRetrievalAdapter(session)
        assert adapter.search_policies(query="") == []
        assert adapter.search_policies(query="   \n\t  ") == []
        assert adapter.search_policies(query=["", "   "]) == []


def test_cli_chunk_policies_and_search() -> None:
    """Verifies standalone CLI chunk-policies and search-policies commands (P3-EV-013)."""
    # 1. Test chunk-policies
    res_chunk = subprocess.run(
        [sys.executable, "-m", "trustdesk.cli", "chunk-policies"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Derived and indexed 9 section(s)" in res_chunk.stdout

    # 2. Test search-policies
    res_search = subprocess.run(
        [sys.executable, "-m", "trustdesk.cli", "search-policies", "refund", "window", "--limit", "3"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "KB-REFUND-001" in res_search.stdout
    assert "Score:" in res_search.stdout
