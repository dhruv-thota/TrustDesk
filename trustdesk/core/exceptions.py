from __future__ import annotations

from typing import Any


class TrustDeskException(Exception):
    """Base exception for all TrustDesk application errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}


class DatabaseConnectionError(TrustDeskException):
    """Raised when the primary database is unreachable."""

    def __init__(
        self,
        message: str = "Database connection unavailable",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="DATABASE_UNAVAILABLE",
            status_code=503,
            details=details,
        )


class AuthenticationError(TrustDeskException):
    """Raised when authentication fails due to missing or invalid bearer token."""

    def __init__(
        self,
        message: str = "Invalid or missing bearer authentication token.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="UNAUTHORIZED",
            status_code=401,
            details=details,
        )


class TicketNotFoundError(TrustDeskException):
    """Raised when a requested ticket ID cannot be found."""

    def __init__(
        self,
        ticket_id: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        formatted_message = message or f"Ticket with ID '{ticket_id}' was not found."
        combined_details = {"ticket_id": ticket_id}
        if details:
            combined_details.update(details)
        super().__init__(
            message=formatted_message,
            error_code="TICKET_NOT_FOUND",
            status_code=404,
            details=combined_details,
        )


class IngestionError(TrustDeskException):
    """Raised when dataset ingestion fails due to missing files or corrupted syntax."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="INGESTION_ERROR",
            status_code=400,
            details=details,
        )


class QuarantinedRecordException(TrustDeskException):
    """Raised when an ingested record violates mandatory parent constraints and is quarantined."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="RECORD_QUARANTINED",
            status_code=400,
            details=details,
        )


class ActionNotFoundError(TrustDeskException):
    """Raised when a requested action UUID cannot be found."""

    def __init__(self, action_id: str, message: str | None = None, details: dict[str, Any] | None = None) -> None:
        formatted_message = message or f"Action with ID '{action_id}' was not found."
        combined_details = {"action_id": str(action_id)}
        if details:
            combined_details.update(details)
        super().__init__(
            message=formatted_message,
            error_code="ACTION_NOT_FOUND",
            status_code=404,
            details=combined_details,
        )


class ActionAlreadyProcessedError(TrustDeskException):
    """Raised when approving/rejecting an action that is not in pending_approval state."""

    def __init__(self, action_id: str, current_status: str, message: str | None = None, details: dict[str, Any] | None = None) -> None:
        formatted_message = message or f"Action with ID '{action_id}' is already in status '{current_status}' and cannot be modified."
        combined_details = {"action_id": str(action_id), "current_status": current_status}
        if details:
            combined_details.update(details)
        super().__init__(
            message=formatted_message,
            error_code="ACTION_ALREADY_PROCESSED",
            status_code=409,
            details=combined_details,
        )


class ActiveReviewExistsError(TrustDeskException):
    """Raised when proposing an action for a ticket that already has an active refund review."""

    def __init__(self, ticket_id: str, message: str | None = None, details: dict[str, Any] | None = None) -> None:
        formatted_message = message or f"Ticket '{ticket_id}' already has an active or executed refund review."
        combined_details = {"ticket_id": ticket_id}
        if details:
            combined_details.update(details)
        super().__init__(
            message=formatted_message,
            error_code="ACTIVE_REVIEW_ALREADY_EXISTS",
            status_code=409,
            details=combined_details,
        )


class IdempotencyConflictError(TrustDeskException):
    """Raised when an idempotency key is reused with a different action ID or payload."""

    def __init__(self, key: str, error_code: str = "IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD", message: str | None = None, details: dict[str, Any] | None = None) -> None:
        formatted_message = message or f"Idempotency key '{key}' was previously used with a different action ID or payload."
        combined_details = {"idempotency_key": key}
        if details:
            combined_details.update(details)
        super().__init__(
            message=formatted_message,
            error_code=error_code,
            status_code=409,
            details=combined_details,
        )


class BusinessRuleViolationError(TrustDeskException):
    """Raised when action execution fails business validation rules (P5-EC-004, U-008)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="BUSINESS_RULE_VIOLATION",
            status_code=422,
            details=details,
        )


class UnsupportedActionError(TrustDeskException):
    """Raised when attempting to propose or execute an operational action not in scope."""

    def __init__(self, action_type: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=f"Action type '{action_type}' is unsupported or strictly out of scope for TrustDesk MVP.",
            error_code="UNSUPPORTED_ACTION",
            status_code=422,
            details={"action_type": action_type, **(details or {})},
        )


class ActiveEvaluationConflictError(TrustDeskException):
    """Raised when an evaluation run is submitted while another is currently active (P7-EC-002)."""

    def __init__(
        self,
        message: str = "An evaluation run is currently active.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="EVAL_ALREADY_RUNNING",
            status_code=409,
            details=details,
        )


class BrokerUnavailableError(TrustDeskException):
    """Raised when the background task broker (Redis) is unreachable (P7-EC-001)."""

    def __init__(
        self,
        message: str = "Background job broker is unreachable.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="REDIS_UNAVAILABLE",
            status_code=503,
            details=details,
        )


class EvaluationNotFoundError(TrustDeskException):
    """Raised when an evaluation run UUID cannot be found in PostgreSQL."""

    def __init__(
        self,
        run_id: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message or f"Evaluation run '{run_id}' was not found.",
            error_code="EVALUATION_NOT_FOUND",
            status_code=404,
            details={"run_id": str(run_id), **(details or {})},
        )


class JobNotFoundError(TrustDeskException):
    """Raised when a background job identifier cannot be found in PostgreSQL."""

    def __init__(
        self,
        job_id: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message or f"Background job '{job_id}' was not found.",
            error_code="JOB_NOT_FOUND",
            status_code=404,
            details={"job_id": job_id, **(details or {})},
        )
