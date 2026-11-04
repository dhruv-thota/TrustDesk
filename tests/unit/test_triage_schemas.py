from __future__ import annotations

import pytest
from pydantic import ValidationError

from trustdesk.schemas.triage import (
    TicketCategory,
    TicketPriority,
    TriageResultSchema,
)


def test_valid_ticket_categories():
    """Verify all permitted categories parse successfully into TicketCategory enum."""
    expected_categories = [
        "shipping",
        "refund",
        "warranty",
        "billing",
        "account_security",
        "general",
    ]
    for cat in expected_categories:
        assert TicketCategory(cat).value == cat


def test_invalid_ticket_category_rejected():
    """Verify disallowed category strings raise ValueError / ValidationError."""
    invalid_categories = ["security", "critical", "unknown", "returns", "complaint", ""]
    for inv in invalid_categories:
        with pytest.raises(ValueError):
            TicketCategory(inv)


def test_valid_ticket_priorities():
    """Verify all permitted priorities parse successfully into TicketPriority enum."""
    expected_priorities = ["low", "medium", "high", "urgent"]
    for prio in expected_priorities:
        assert TicketPriority(prio).value == prio


def test_invalid_ticket_priority_rejected():
    """Verify disallowed priority strings raise ValueError / ValidationError."""
    invalid_priorities = ["p1", "critical", "immediate", "normal", ""]
    for inv in invalid_priorities:
        with pytest.raises(ValueError):
            TicketPriority(inv)


def test_triage_result_schema_valid():
    """Verify TriageResultSchema parses valid dictionary representation."""
    payload = {
        "category": "refund",
        "priority": "high",
        "needs_escalation": False,
        "reasoning": "Customer is requesting a refund for an eligible order.",
        "is_fallback": False,
        "sanitized_diagnostics": {"model": "test-mock"},
    }
    result = TriageResultSchema.model_validate(payload)
    assert result.category == TicketCategory.REFUND
    assert result.priority == TicketPriority.HIGH
    assert result.needs_escalation is False
    assert result.is_fallback is False
    assert result.sanitized_diagnostics["model"] == "test-mock"


def test_triage_result_schema_missing_fields_rejected():
    """Verify missing required fields raise ValidationError."""
    with pytest.raises(ValidationError):
        TriageResultSchema.model_validate({"category": "shipping"})


def test_triage_result_schema_invalid_category_rejected():
    """Verify invalid category within TriageResultSchema triggers ValidationError."""
    with pytest.raises(ValidationError):
        TriageResultSchema.model_validate({
            "category": "invalid_category",
            "priority": "medium",
            "needs_escalation": False,
            "reasoning": "Some explanation",
        })


def test_triage_result_schema_invalid_priority_rejected():
    """Verify invalid priority within TriageResultSchema triggers ValidationError."""
    with pytest.raises(ValidationError):
        TriageResultSchema.model_validate({
            "category": "billing",
            "priority": "critical",
            "needs_escalation": False,
            "reasoning": "Some explanation",
        })


def test_triage_result_schema_defaults():
    """Verify defaults for is_fallback and sanitized_diagnostics."""
    result = TriageResultSchema(
        category=TicketCategory.GENERAL,
        priority=TicketPriority.LOW,
        needs_escalation=False,
        reasoning="Simple query",
    )
    assert result.is_fallback is False
    assert result.sanitized_diagnostics == {}

