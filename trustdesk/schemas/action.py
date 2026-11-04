from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class ActionProposalCreateSchema(BaseModel):
    """Payload to propose an operational refund review."""

    model_config = ConfigDict(from_attributes=True)

    action_type: Literal["start_refund_review"] = Field(
        default="start_refund_review",
        description="Operational action type. Fixed to 'start_refund_review' in MVP.",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Action operational parameters (e.g. order_id, reason, requested_amount)",
    )
    notes: str | None = Field(
        default=None,
        description="Optional justification or recommendation notes",
    )


class ProposedActionSchema(BaseModel):
    """Complete representation of a proposed operational action."""

    model_config = ConfigDict(from_attributes=True)

    action_id: uuid.UUID = Field(description="Unique action UUID")
    ticket_id: str = Field(description="Target ticket identifier")
    action_type: str = Field(description="Action type, e.g. 'start_refund_review'")
    status: str = Field(description="Canonical state: pending_approval, rejected, executed, failed")
    action_payload: dict[str, Any] = Field(default_factory=dict, description="Action parameters")
    proposed_by: str = Field(description="Originator of proposal: 'ai' or 'agent'")
    reviewed_by: str | None = Field(default=None, description="Server-verified agent identifier who reviewed")
    review_notes: str | None = Field(default=None, description="Human reviewer comments")
    created_at: datetime = Field(description="Timestamp when proposed")
    reviewed_at: datetime | None = Field(default=None, description="Timestamp when reviewed")
    executed_at: datetime | None = Field(default=None, description="Timestamp when executed")


class ActionApproveRequestSchema(BaseModel):
    """Request payload for approving a pending operational action."""

    model_config = ConfigDict(from_attributes=True)

    notes: str | None = Field(default=None, description="Human agent approval notes")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional adjusted parameters for execution",
    )


class ActionRejectRequestSchema(BaseModel):
    """Request payload for rejecting a pending operational action."""

    model_config = ConfigDict(from_attributes=True)

    reason: str | None = Field(default=None, description="Reason for rejecting the recommendation")
    notes: str | None = Field(default=None, description="Additional agent rejection comments")


class ActionExecutionResultSchema(BaseModel):
    """Result returned upon executing an approved operational action."""

    model_config = ConfigDict(from_attributes=True)

    action_id: uuid.UUID = Field(description="Action identifier")
    ticket_id: str = Field(description="Ticket identifier")
    action_type: str = Field(description="Action type executed")
    status: str = Field(description="Execution outcome: 'executed' or 'failed'")
    reviewed_by: str = Field(description="Server-verified agent identifier")
    reviewed_at: datetime = Field(description="Approval timestamp")
    executed_at: datetime | None = Field(default=None, description="Execution timestamp")
    execution_details: dict[str, Any] = Field(
        default_factory=dict,
        description="Formal review registration details",
    )
    error_details: dict[str, Any] | None = Field(
        default=None,
        description="Failure details if status is failed",
    )

