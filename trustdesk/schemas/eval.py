from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from trustdesk.schemas.ticket import (
    CustomerProfileSchema,
    OrderDetailSchema,
    TicketDetailSchema,
)
from trustdesk.schemas.triage import TicketCategory, TicketPriority


class ExpectedTriageSchema(BaseModel):
    """Ground-truth expectations for AI ticket classification."""

    model_config = ConfigDict(extra="forbid")

    category: TicketCategory
    priority: TicketPriority
    needs_escalation: bool = False


class ExpectedActionSchema(BaseModel):
    """Ground-truth expectations for advisory action recommendation."""

    model_config = ConfigDict(extra="forbid")

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
        description="Expected parameters for the proposed action",
    )
    reasoning: str | None = Field(
        default=None,
        description="Expected rationale for recommendation",
    )


class GuardrailExpectationsSchema(BaseModel):
    """Ground-truth safety, secret-leak, and action-blocking expectations."""

    model_config = ConfigDict(extra="forbid")

    expected_guardrail_outcome: str = Field(
        default="passed",
        description="Expected guardrail check outcome: 'passed' or 'flagged'",
    )
    forbid_unapproved_action: bool = Field(
        default=True,
        description="Enforces that no autonomous operational action was executed",
    )
    forbid_secret_leak: bool = Field(
        default=True,
        description="Enforces that system prompt or internal secrets are not disclosed",
    )
    forbidden_tokens: list[str] = Field(
        default_factory=list,
        description="Specific substring tokens strictly forbidden from generated output",
    )


class EvaluationCaseSchema(BaseModel):
    """Complete, self-contained specification for a single evaluation dataset line."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique business identifier for evaluation case (e.g. EVAL-001)",
    )
    description: str = Field(
        ...,
        min_length=1,
        description="Human-readable description of the evaluation test scenario",
    )
    scenario_type: str = Field(
        ...,
        min_length=1,
        description="Semantic category of test scenario (e.g. refund_eligible, security_incident)",
    )
    ticket: TicketDetailSchema = Field(
        ...,
        description="Self-contained support ticket fixture",
    )
    customer: CustomerProfileSchema = Field(
        ...,
        description="Self-contained customer profile fixture",
    )
    order: OrderDetailSchema | None = Field(
        default=None,
        description="Linked order details if applicable, or None",
    )
    expected_triage: ExpectedTriageSchema | None = Field(
        default=None,
        description="Expected triage labels, or None if case is inconclusive (EVAL-017)",
    )
    expected_draft_escalation: bool | None = Field(
        default=None,
        description="Expected draft escalation recommendation, or None if inconclusive",
    )
    expected_citations: list[str] = Field(
        default_factory=list,
        description="List of expected parent KB IDs (e.g. ['KB-REFUND-001'])",
    )
    expected_action: ExpectedActionSchema | None = Field(
        default=None,
        description="Expected advisory action recommendation outcome",
    )
    is_adversarial: bool = Field(
        default=False,
        description="Flag indicating if the case tests guardrails/injections",
    )
    adversarial_type: str | None = Field(
        default=None,
        description="Type of adversarial test (e.g. prompt_injection, knowledge_poisoning)",
    )
    guardrail_expectations: GuardrailExpectationsSchema = Field(
        default_factory=GuardrailExpectationsSchema,
        description="Security and action-blocking assertions",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional test fixture metadata and parameters",
    )


class ValidatedLine(BaseModel):
    """Line-level evaluation validation outcome matching EvalResult.validation_status."""

    model_config = ConfigDict(extra="forbid")

    source_line_number: int = Field(
        ...,
        ge=1,
        description="1-indexed line position in the source dataset file",
    )
    validation_status: str = Field(
        ...,
        description="Status: 'valid', 'inconclusive', or 'malformed_input'",
    )
    case_id: str | None = Field(
        default=None,
        description="Case identifier if parseable, or None",
    )
    case: EvaluationCaseSchema | None = Field(
        default=None,
        description="Validated evaluation case instance if valid/inconclusive",
    )
    error_details: dict[str, Any] | None = Field(
        default=None,
        description="Structured diagnostics for malformed or invalid inputs",
    )
    raw_content: str | None = Field(
        default=None,
        description="Raw string of the line if malformed (redacted if sensitive)",
    )


class DatasetValidationResult(BaseModel):
    """Aggregate dataset validation summary matching input accounting invariants."""

    model_config = ConfigDict(extra="forbid")

    total_lines: int = Field(
        default=0,
        ge=0,
        description="Total non-empty input lines evaluated",
    )
    valid_cases_count: int = Field(
        default=0,
        ge=0,
        description="Count of valid cases with complete ground truth",
    )
    inconclusive_count: int = Field(
        default=0,
        ge=0,
        description="Count of valid cases missing ground truth (e.g. EVAL-017)",
    )
    malformed_count: int = Field(
        default=0,
        ge=0,
        description="Count of malformed JSON or schema-invalid lines",
    )
    lines: list[ValidatedLine] = Field(
        default_factory=list,
        description="Ordered line-by-line validation records",
    )
    is_valid: bool = Field(
        default=True,
        description="False if fatal errors or malformed lines prevent clean execution",
    )
    fatal_error: str | None = Field(
        default=None,
        description="Fatal pre-flight abort message if file is missing, empty, or unreadable",
    )


class MetricScore(BaseModel):
    """Auditable rate with explicit numerator and denominator."""

    model_config = ConfigDict(extra="forbid")

    rate: float | None = Field(
        default=None,
        description="Quotient of numerator / denominator, or null if denominator is zero",
    )
    numerator: int = Field(default=0, ge=0)
    denominator: int = Field(default=0, ge=0)


class PrecisionRecallScore(BaseModel):
    """Auditable precision and recall metrics with confusion counts."""

    model_config = ConfigDict(extra="forbid")

    precision: float | None = Field(
        default=None,
        description="TP / (TP + FP), or null if denominator is zero",
    )
    recall: float | None = Field(
        default=None,
        description="TP / (TP + FN), or null if denominator is zero",
    )
    true_positives: int = Field(default=0, ge=0)
    false_positives: int = Field(default=0, ge=0)
    false_negatives: int = Field(default=0, ge=0)
    true_negatives: int = Field(default=0, ge=0)


class InputAccounting(BaseModel):
    """Complete execution input accounting invariant."""

    model_config = ConfigDict(extra="forbid")

    total_lines: int = Field(default=0, ge=0)
    evaluated: int = Field(default=0, ge=0)
    inconclusive: int = Field(default=0, ge=0)
    invalid_input: int = Field(default=0, ge=0)
    model_failure: int = Field(default=0, ge=0)
    is_valid: bool = Field(
        default=True,
        description="True if total_lines == evaluated + inconclusive + invalid_input + model_failure",
    )


class CaseEvaluationOutcome(BaseModel):
    """Line-level outcome record for an evaluation run case."""

    model_config = ConfigDict(extra="forbid")

    source_line_number: int = Field(..., ge=1)
    case_id: str | None = None
    ticket_id: str | None = None
    validation_status: str = Field(
        default="valid",
        description="'valid', 'evaluated', 'inconclusive', 'invalid_input', 'malformed_input', 'model_failure'",
    )
    # Ground truth expectations
    expected_triage: ExpectedTriageSchema | None = None
    expected_draft_escalation: bool | None = None
    expected_citations: list[str] = Field(default_factory=list)
    expected_action: ExpectedActionSchema | None = None
    is_adversarial: bool = False
    guardrail_expectations: GuardrailExpectationsSchema = Field(default_factory=GuardrailExpectationsSchema)

    # Actual model / workflow outputs
    actual_category: str | None = None
    actual_priority: str | None = None
    actual_triage_escalation: bool | None = None
    actual_draft_escalation: bool | None = None
    actual_cited_kb_ids: list[str] = Field(default_factory=list)
    has_valid_provenance: bool | None = None
    is_grounded: bool | None = None
    action_recommended: bool | None = None
    unapproved_action_executed: bool = False
    secret_leaked: bool = False
    guardrail_check_passed: bool = True

    # Evaluated dimension verdicts
    triage_passed: bool = False
    citation_passed: bool = False
    safety_passed: bool = False
    escalation_passed: bool = False
    case_passed: bool = False
    execution_details: dict[str, Any] = Field(default_factory=dict)


class MetricsSummary(BaseModel):
    """Authoritative, JSON-serializable evaluation metrics report matching U-009."""

    model_config = ConfigDict(extra="forbid")

    # Input accounting
    input_accounting: InputAccounting

    # Triage accuracies
    joint_triage_accuracy: MetricScore
    category_accuracy: MetricScore
    priority_accuracy: MetricScore

    # Separated escalation metrics
    triage_escalation: PrecisionRecallScore
    draft_escalation: PrecisionRecallScore

    # Citation & grounding metrics
    citation_provenance_validity: MetricScore
    expected_citation_coverage: MetricScore
    policy_grounding_rate: MetricScore

    # Safety & action blocking
    autonomous_execution_prevention: MetricScore
    action_recommendation_accuracy: MetricScore
    adversarial_safety_rate: MetricScore

    # Overall totals
    total_cases: int = Field(default=0, ge=0)
    passed_cases: int = Field(default=0, ge=0)
    overall_pass_rate: MetricScore


# ---------------------------------------------------------------------------
# Canonical Dataset Path Validation (Security Invariant)
# ---------------------------------------------------------------------------

def get_approved_data_dir() -> Path:
    """Resolve and return the canonical absolute path of the approved project data/ directory."""
    project_root = Path(__file__).resolve().parents[2]
    return (project_root / "data").resolve()


def validate_canonical_dataset_path(
    dataset_path: str | Path,
    approved_data_dir: Path | None = None,
) -> Path:
    """Validate and resolve a dataset path ensuring canonical containment within approved_data_dir.

    Enforces:
    1. Rejection of empty strings, null bytes ('\0'), and path traversal ('..').
    2. Rejection of non-.jsonl extensions.
    3. Canonical resolution of both approved directory and target path (following symlinks).
    4. Rejection of paths whose canonical target resolves outside the approved directory
       (including symlink escapes pointing outside data/).
    5. Rejection if target is the directory itself rather than a regular file path.
    6. Preservation of legitimate relative dataset paths (e.g. './data/eval_cases.jsonl').

    Returns:
        The canonical, fully resolved Path within approved_data_dir.

    Raises:
        ValueError: If validation fails for any security or containment rule.
    """
    if not dataset_path:
        raise ValueError("Dataset path cannot be empty.")

    raw_str = str(dataset_path).strip()
    if not raw_str:
        raise ValueError("Dataset path cannot be empty.")

    if "\x00" in raw_str:
        raise ValueError("Path traversal detected: dataset_path cannot contain null bytes.")

    if ".." in raw_str:
        raise ValueError("Path traversal detected: dataset_path cannot contain '..' sequences.")

    if not raw_str.endswith(".jsonl"):
        raise ValueError("Invalid file extension: dataset file must have a .jsonl extension.")

    approved_dir = (approved_data_dir or get_approved_data_dir()).resolve()

    path_obj = Path(raw_str)
    # If path is relative, anchor it to project_root (approved_dir.parent)
    if not path_obj.is_absolute():
        candidate = (approved_dir.parent / path_obj).resolve()
    else:
        candidate = path_obj.resolve()

    try:
        is_inside = candidate.is_relative_to(approved_dir)
    except (ValueError, AttributeError):
        is_inside = False

    if not is_inside or candidate == approved_dir:
        raise ValueError(
            f"Access denied: dataset path '{raw_str}' resolves to '{candidate}', "
            f"which is outside the approved data directory '{approved_dir}'."
        )

    if candidate.exists() and not candidate.is_file():
        raise ValueError(f"Invalid dataset target: '{candidate}' is not a regular file.")

    return candidate


# ---------------------------------------------------------------------------
# Phase 7 REST API Request & Response Schemas
# ---------------------------------------------------------------------------

class EvaluationRunRequestSchema(BaseModel):
    """Request payload for triggering an asynchronous evaluation run."""

    model_config = ConfigDict(extra="forbid")

    dataset_path: str = Field(
        default="./data/eval_cases.jsonl",
        description="Path to evaluation dataset JSONL file",
    )

    @field_validator("dataset_path")
    @classmethod
    def validate_dataset_path(cls, v: str) -> str:
        validate_canonical_dataset_path(v)
        return v



class EvaluationRunResponseSchema(BaseModel):
    """Response payload returned when an evaluation run is accepted for background execution."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    job_id: str
    status: str = "queued"
    message: str = "Evaluation run accepted and enqueued for background processing."


class JobStatusResponseSchema(BaseModel):
    """Response payload for background job polling."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    run_id: str
    status: str
    total_cases: int = 0
    passed_cases: int = 0
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_details: dict[str, Any] | None = None


class EvaluationSummarySchema(BaseModel):
    """Summary item for evaluation history listing."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    job_id: str
    status: str
    total_cases: int = 0
    passed_cases: int = 0
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_details: dict[str, Any] | None = None


class EvaluationListResponseSchema(BaseModel):
    """Paginated list of evaluation runs."""

    model_config = ConfigDict(extra="forbid")

    items: list[EvaluationSummarySchema]
    total: int
    limit: int
    offset: int


class EvaluationResultItemSchema(BaseModel):
    """Per-case evaluation result record item."""

    model_config = ConfigDict(extra="forbid")

    id: str
    run_id: str
    source_line_number: int
    case_id: str | None = None
    ticket_id: str | None = None
    validation_status: str
    triage_passed: bool
    citation_passed: bool
    safety_passed: bool
    escalation_passed: bool
    execution_details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class EvaluationDetailResponseSchema(BaseModel):
    """Detailed evaluation run report with full metrics and per-case results."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    job_id: str
    status: str
    total_cases: int = 0
    passed_cases: int = 0
    metrics_summary: dict[str, Any] = Field(default_factory=dict)
    error_details: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    results: list[EvaluationResultItemSchema] = Field(default_factory=list)


