from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trustdesk.schemas.triage import (
    TicketCategory,
    TicketPriority,
    TriageResultSchema,
)
from trustdesk.services.ai.live_provider import LiveAIProvider
from trustdesk.services.ai.mock_provider import MockAIProvider
from trustdesk.services.triage_service import triage_ticket_service


@pytest.mark.asyncio
async def test_mock_provider_timeout_simulation():
    """Verify MockAIProvider raises TimeoutError when simulate_timeout is provided."""
    provider = MockAIProvider()
    with pytest.raises(TimeoutError, match="simulated timeout"):
        await provider.triage_ticket(
            ticket_subject="Need help",
            ticket_message="Please assist, simulate_timeout in request",
        )


@pytest.mark.asyncio
async def test_mock_provider_malformed_simulation():
    """Verify MockAIProvider raises ValueError when simulate_malformed is provided."""
    provider = MockAIProvider()
    with pytest.raises(ValueError, match="unparseable malformed output"):
        await provider.triage_ticket(
            ticket_subject="simulate_malformed",
            ticket_message="Broken data",
        )


@pytest.mark.asyncio
async def test_triage_service_fallback_on_provider_timeout():
    """Verify triage_service catches timeout and returns safe fallback triage object."""
    mock_provider = MockAIProvider()
    mock_ticket = MagicMock(
        ticket_id="TIK-TIMEOUT",
        subject="Need help",
        message="Please simulate_timeout now",
    )
    mock_db = MagicMock()

    with patch("trustdesk.services.ticket_service.get_ticket", return_value=mock_ticket):
        triage_record = await triage_ticket_service(
            db=mock_db,
            ticket_id="TIK-TIMEOUT",
            provider=mock_provider,
        )

    assert triage_record.is_fallback is True
    assert triage_record.category == TicketCategory.GENERAL.value
    assert triage_record.priority == TicketPriority.MEDIUM.value
    assert triage_record.needs_escalation is True
    assert "fallback" in triage_record.reasoning.lower()
    assert triage_record.sanitized_diagnostics["error_type"] == "TimeoutError"
    assert mock_db.add.called
    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_triage_service_fallback_on_provider_malformed_output():
    """Verify triage_service catches malformed output and returns safe fallback triage object."""
    mock_provider = MockAIProvider()
    mock_ticket = MagicMock(
        ticket_id="TIK-MALFORMED",
        subject="Broken json",
        message="Test with simulate_malformed data",
    )
    mock_db = MagicMock()

    with patch("trustdesk.services.ticket_service.get_ticket", return_value=mock_ticket):
        triage_record = await triage_ticket_service(
            db=mock_db,
            ticket_id="TIK-MALFORMED",
            provider=mock_provider,
        )

    assert triage_record.is_fallback is True
    assert triage_record.category == TicketCategory.GENERAL.value
    assert triage_record.priority == TicketPriority.MEDIUM.value
    assert triage_record.needs_escalation is True
    assert triage_record.sanitized_diagnostics["error_type"] == "ValueError"
    assert mock_db.add.called
    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_live_provider_timeout_and_retry():
    """Verify LiveAIProvider enforces timeout and bounded retry with backoff."""
    provider = LiveAIProvider(
        api_key="mock_key",
        model_name="gemini-3.8-flash",
        timeout_seconds=0.05,
        max_retries=1,
        retry_delay_seconds=0.01,
    )

    # Mock client.aio.models.generate_content to hang longer than timeout
    async def slow_call(*args, **kwargs):
        await asyncio.sleep(0.5)
        return MagicMock(text='{"category": "general", "priority": "low", "needs_escalation": false, "reasoning": "done"}')

    provider.client.aio.models.generate_content = slow_call

    with pytest.raises(TimeoutError, match="timed out after 0.05s"):
        await provider.triage_ticket(
            ticket_subject="Hello",
            ticket_message="World",
        )


@pytest.mark.asyncio
async def test_live_provider_missing_api_key_rejected():
    """Verify LiveAIProvider requires non-empty api_key."""
    with pytest.raises(ValueError, match="GEMINI_API_KEY must be provided"):
        LiveAIProvider(api_key="")
