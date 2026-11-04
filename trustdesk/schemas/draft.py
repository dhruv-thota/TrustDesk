from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class DraftCitationSchema(BaseModel):
    """Citation reference within a generated draft."""

    model_config = ConfigDict(from_attributes=True)

    kb_id: str = Field(description="Parent policy identifier, e.g. KB-REFUND-001")
    section_id: str = Field(description="Deterministic section reference, e.g. KB-REFUND-001#sec-1")
    quoted_snippet: str | None = Field(default=None, description="Direct supporting snippet from section")
    is_valid_provenance: bool = Field(default=True, description="True if section existed in retrieved evidence")


class ActionRecommendationSchema(BaseModel):
    """Advisory action recommendation proposed by AI."""

    model_config = ConfigDict(from_attributes=True)

    action_type: str = Field(
        default="start_refund_review",
        description="Action type identifier, strictly 'start_refund_review'",
    )
    should_recommend: bool = Field(
        default=False,
        description="True if context warrants initiating the action",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Action parameters for proposal (e.g. order_id, reason)",
    )
    reasoning: str = Field(
        default="",
        description="Justification for recommendation",
    )


class DraftResponseSchema(BaseModel):
    """Policy-grounded response draft payload."""

    model_config = ConfigDict(from_attributes=True)

    ticket_id: str
    draft_text: str
    citations: list[DraftCitationSchema] = Field(default_factory=list)
    has_valid_provenance: bool = Field(
        description="Level 1: True if all cited section IDs exist in retrieved evidence",
    )
    is_grounded: bool = Field(
        description="Level 3: True if Level 1 passed and deterministic policy facts are consistent",
    )
    escalation_suggested: bool = Field(
        description="True if evidence is missing, uncertain, or policy facts contradicted",
    )
    escalation_reason: str | None = Field(
        default=None,
        description="Reason for escalation if applicable",
    )
    suggested_action: ActionRecommendationSchema | None = Field(
        default=None,
        description="Advisory action recommendation if evaluated",
    )
    sanitized_diagnostics: dict[str, Any] = Field(
        default_factory=dict,
        description="Redacted telemetry without PII or raw prompts",
    )

