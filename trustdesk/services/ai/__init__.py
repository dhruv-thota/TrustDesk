from __future__ import annotations

from trustdesk.core.config import settings
from trustdesk.services.ai.base import AIProviderAdapter
from trustdesk.services.ai.live_provider import LiveAIProvider
from trustdesk.services.ai.mock_provider import MockAIProvider
from trustdesk.services.ai.openrouter_provider import OpenRouterAIProvider


def get_ai_provider(provider_override: AIProviderAdapter | None = None) -> AIProviderAdapter:
    """Dependency provider returning the configured AIProviderAdapter instance."""
    if provider_override is not None:
        return provider_override

    provider_name = settings.ai_provider.lower()

    if provider_name == "openrouter":
        api_key = settings.effective_openrouter_api_key
        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY (or OPENAI_API_KEY) environment variable is missing for openrouter AI provider."
            )
        return OpenRouterAIProvider(
            api_key=api_key,
            base_url=settings.effective_openrouter_base_url,
            model_name=settings.openrouter_model,
            timeout_seconds=settings.openrouter_timeout_seconds,
            max_retries=settings.openrouter_max_retries,
            site_url=settings.openrouter_site_url,
            site_name=settings.openrouter_site_name,
        )

    if provider_name == "live":
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
    "OpenRouterAIProvider",
    "get_ai_provider",
]

