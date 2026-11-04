from __future__ import annotations

from datetime import datetime, timezone
import pytest

from trustdesk.schemas.draft import ActionRecommendationSchema, DraftCitationSchema
from trustdesk.services.citation_service import validate_citation_provenance
from trustdesk.services.draft_service import (
    _check_snippet_support,
    _detect_unauthorized_discount,
)
from trustdesk.services.retrieval.base import CitationRef, PolicySectionMatch


def test_level1_citation_provenance_valid():
    """Verify valid citations matching retrieved evidence pass Level 1 provenance."""
    evidence = [
        PolicySectionMatch(
            kb_id="KB-REFUND-001",
            section_id="KB-REFUND-001#sec-0",
            section_title="Overview",
            content="Return window is 30 calendar days from confirmed delivery date.",
        ),
        PolicySectionMatch(
            kb_id="KB-REFUND-001",
            section_id="KB-REFUND-001#sec-1",
            section_title="Condition",
            content="Original packaging is required for all returns.",
        ),
    ]

    cited = [
        CitationRef(kb_id="KB-REFUND-001", section_id="KB-REFUND-001#sec-0"),
        CitationRef(kb_id="KB-REFUND-001", section_id="KB-REFUND-001#sec-1"),
    ]

    result = validate_citation_provenance(cited_sections=cited, retrieved_sections=evidence)
    assert result.has_valid_provenance is True
    assert len(result.invalid_citations) == 0


def test_level1_citation_provenance_hallucinated_section_rejected():
    """Verify unretrieved section reference fails Level 1 provenance."""
    evidence = [
        PolicySectionMatch(
            kb_id="KB-REFUND-001",
            section_id="KB-REFUND-001#sec-0",
            section_title="Overview",
            content="Content here",
        ),
    ]

    cited = [
        CitationRef(kb_id="KB-REFUND-001", section_id="KB-REFUND-001#sec-99"),
    ]

    result = validate_citation_provenance(cited_sections=cited, retrieved_sections=evidence)
    assert result.has_valid_provenance is False
    assert len(result.invalid_citations) == 1
    assert result.invalid_citations[0].section_id == "KB-REFUND-001#sec-99"


def test_level2_snippet_support_matching():
    """Verify exact or normalized quoted snippets pass Level 2 support check."""
    section_content = (
        "Customers may return eligible hardware products within 30 calendar days "
        "from the date of confirmed delivery."
    )
    snippet = "return eligible hardware products within 30 calendar days"
    assert _check_snippet_support(snippet, section_content) is True


def test_level2_snippet_support_non_matching_rejected():
    """Verify fabricated snippet fails Level 2 support check."""
    section_content = "Customers may return eligible hardware products within 30 calendar days."
    fabricated_snippet = "Customers are entitled to an instant cash payout with no questions asked."
    assert _check_snippet_support(fabricated_snippet, section_content) is False


def test_level2_unauthorized_discount_detection():
    """Verify promotional commitments without promotional policy are detected as violations."""
    evidence = [
        PolicySectionMatch(
            kb_id="KB-REFUND-001",
            section_id="KB-REFUND-001#sec-0",
            section_title="Standard Return Policy",
            content="Standard refund rules.",
        ),
    ]

    draft_with_discount = (
        "We are pleased to offer you a 25% discount coupon on your next order: PROMO25."
    )
    assert _detect_unauthorized_discount(draft_with_discount, evidence) is True

    draft_without_discount = (
        "Your order was dispatched yesterday and will arrive in 3 to 5 business days."
    )
    assert _detect_unauthorized_discount(draft_without_discount, evidence) is False


def test_advisory_action_recommendation_contract():
    """Verify ActionRecommendationSchema defaults and advisory structure."""
    rec = ActionRecommendationSchema(
        action_type="start_refund_review",
        should_recommend=True,
        payload={"order_id": "ORD-123"},
        reasoning="Within 30 days",
    )
    assert rec.action_type == "start_refund_review"
    assert rec.should_recommend is True
    assert rec.payload["order_id"] == "ORD-123"
    assert "Within 30 days" in rec.reasoning

