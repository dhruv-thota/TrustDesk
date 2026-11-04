from __future__ import annotations

from trustdesk.core.config import settings
from trustdesk.services.ai.base import AIProviderAdapter
from trustdesk.services.ai.live_provider import LiveAIProvider
from trustdesk.services.ai.mock_provider import MockAIProvider


def get_ai_provider(provider_override: AIProviderAdapter | None = None) -> AIProviderAdapter:
    """Dependency provider returning the configured AIProviderAdapter instance."""
    if provider_override is not None:
        return provider_override

    if settings.ai_provider == "live":
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY environment variable is missing for live AI provider.")
        return LiveAIProvider(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_model,
        )

    return MockAIProvider()


__all__ = [
    "AIProviderAdapter",
    "LiveAIProvider",
    "MockAIProvider",
    "get_ai_provider",
]

