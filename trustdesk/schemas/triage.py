from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TicketCategory(str, Enum):
    """Permitted ticket issue categories."""

    SHIPPING = "shipping"
    REFUND = "refund"
    WARRANTY = "warranty"
    BILLING = "billing"
    ACCOUNT_SECURITY = "account_security"
    GENERAL = "general"


class TicketPriority(str, Enum):
    """Permitted ticket operational priorities."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TriageResultSchema(BaseModel):
    """Structured AI ticket classification outcome."""

    model_config = ConfigDict(from_attributes=True)

    category: TicketCategory
    priority: TicketPriority
    needs_escalation: bool
    reasoning: str = Field(..., max_length=1000)
    is_fallback: bool = Field(default=False, description="True if classification is an AI failure fallback")
    sanitized_diagnostics: dict[str, Any] = Field(
        default_factory=dict,
        description="Redacted telemetry and error codes without PII or raw prompts",
    )

