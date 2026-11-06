"""TrustDesk Evaluation Engine and Dataset Verification."""
from __future__ import annotations

from typing import TYPE_CHECKING

from trustdesk.eval.loader import (
    DatasetEmptyError,
    DatasetNotFoundError,
    DatasetUnreadableError,
    DatasetValidationError,
    DuplicateCaseIDError,
    load_and_validate_dataset,
)
from trustdesk.eval.metrics import (
    calculate_citation_metrics,
    calculate_draft_escalation,
    calculate_input_accounting,
    calculate_metrics,
    calculate_safety_metrics,
    calculate_triage_accuracy,
    calculate_triage_escalation,
    score_case_outcome,
)

if TYPE_CHECKING:
    from trustdesk.eval.runner import (
        ActiveEvaluationAlreadyRunningError,
        EvaluationRunner,
        RunAlreadyCompletedError,
        RunAlreadyFailedError,
    )

__all__ = [
    "ActiveEvaluationAlreadyRunningError",
    "DatasetEmptyError",
    "DatasetNotFoundError",
    "DatasetUnreadableError",
    "DatasetValidationError",
    "DuplicateCaseIDError",
    "EvaluationRunner",
    "RunAlreadyCompletedError",
    "RunAlreadyFailedError",
    "calculate_citation_metrics",
    "calculate_draft_escalation",
    "calculate_input_accounting",
    "calculate_metrics",
    "calculate_safety_metrics",
    "calculate_triage_accuracy",
    "calculate_triage_escalation",
    "load_and_validate_dataset",
    "score_case_outcome",
]


def __getattr__(name: str) -> object:
    if name in (
        "EvaluationRunner",
        "ActiveEvaluationAlreadyRunningError",
        "RunAlreadyCompletedError",
        "RunAlreadyFailedError",
    ):
        from trustdesk.eval import runner

        return getattr(runner, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


