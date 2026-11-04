from __future__ import annotations

import pytest

from trustdesk.services.citation_service import validate_citation_provenance
from trustdesk.services.retrieval.base import CitationRef, PolicySectionMatch


@pytest.fixture
def sample_retrieved_evidence() -> list[PolicySectionMatch]:
    return [
        PolicySectionMatch(
            kb_id="KB-REFUND-001",
            section_id="KB-REFUND-001#sec-0",
            section_title="1. Overview and Eligibility Window",
            content="Customers may return eligible hardware products within 30 calendar days.",
            relevance_score=0.85,
        ),
        PolicySectionMatch(
            kb_id="KB-REFUND-001",
            section_id="KB-REFUND-001#sec-1",
            section_title="2. Product Condition and Requirements",
            content="Items must be returned in their original packaging.",
            relevance_score=0.72,
        ),
        PolicySectionMatch(
            kb_id="KB-SHIPPING-001",
            section_id="KB-SHIPPING-001#sec-0",
            section_title="1. Fulfillment Timelines",
            content="Standard shipping orders are dispatched within 1 to 2 business days.",
            relevance_score=0.65,
        ),
    ]


def test_valid_citation_provenance(sample_retrieved_evidence: list[PolicySectionMatch]) -> None:
    """Verifies that citations present in retrieved evidence pass validation (P3-EV-010)."""
    cited = [
        CitationRef(kb_id="KB-REFUND-001", section_id="KB-REFUND-001#sec-0", quoted_snippet="30 calendar days"),
        CitationRef(kb_id="KB-SHIPPING-001", section_id="KB-SHIPPING-001#sec-0", quoted_snippet="1 to 2 business days"),
    ]

    result = validate_citation_provenance(
        cited_sections=cited,
        retrieved_sections=sample_retrieved_evidence,
    )

    assert result.has_valid_provenance is True
    assert result.invalid_citations == []
    assert result.insufficient_evidence is False


def test_hallucinated_citation_provenance_rejected(sample_retrieved_evidence: list[PolicySectionMatch]) -> None:
    """Verifies that citations referencing unretrieved sections fail validation (P3-EV-011, P3-EC-003)."""
    cited = [
        CitationRef(kb_id="KB-REFUND-001", section_id="KB-REFUND-001#sec-0"),
        CitationRef(kb_id="KB-REFUND-001", section_id="KB-REFUND-001#sec-99"),  # Hallucinated section!
    ]

    result = validate_citation_provenance(
        cited_sections=cited,
        retrieved_sections=sample_retrieved_evidence,
    )

    assert result.has_valid_provenance is False
    assert len(result.invalid_citations) == 1
    assert result.invalid_citations[0].section_id == "KB-REFUND-001#sec-99"
    assert result.insufficient_evidence is False


def test_unknown_parent_kb_id_rejected(sample_retrieved_evidence: list[PolicySectionMatch]) -> None:
    """Verifies that citations referencing an unrecognized parent policy fail validation (P3-EC-008)."""
    cited = [
        CitationRef(kb_id="KB-UNKNOWN-999", section_id="KB-UNKNOWN-999#sec-0"),
    ]

    result = validate_citation_provenance(
        cited_sections=cited,
        retrieved_sections=sample_retrieved_evidence,
    )

    assert result.has_valid_provenance is False
    assert len(result.invalid_citations) == 1
    assert result.invalid_citations[0].kb_id == "KB-UNKNOWN-999"


def test_empty_retrieved_evidence_insufficient_evidence() -> None:
    """Verifies that an empty evidence set flags insufficient_evidence = True (P3-EV-009, P3-EC-001)."""
    cited = [CitationRef(kb_id="KB-REFUND-001", section_id="KB-REFUND-001#sec-0")]

    result = validate_citation_provenance(
        cited_sections=cited,
        retrieved_sections=[],
    )

    assert result.insufficient_evidence is True
    assert result.has_valid_provenance is False
    assert len(result.invalid_citations) == 1


def test_empty_citations_valid(sample_retrieved_evidence: list[PolicySectionMatch]) -> None:
    """Verifies that an empty citation list is trivially valid (P3-EC-010)."""
    result = validate_citation_provenance(
        cited_sections=[],
        retrieved_sections=sample_retrieved_evidence,
    )

    assert result.has_valid_provenance is True
    assert result.invalid_citations == []
    assert result.insufficient_evidence is False


def test_empty_citations_and_empty_retrieved() -> None:
    """Verifies empty citation list with empty evidence cleanly signals insufficient_evidence."""
    result = validate_citation_provenance(
        cited_sections=[],
        retrieved_sections=[],
    )

    assert result.has_valid_provenance is True
    assert result.invalid_citations == []
    assert result.insufficient_evidence is True

