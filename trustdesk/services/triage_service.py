from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from trustdesk.core.logging import get_logger
from trustdesk.models.ai import ExecutionTrace, TriageResult
from trustdesk.schemas.triage import (
    TicketCategory,
    TicketPriority,
    TriageResultSchema,
)
from trustdesk.services import ticket_service
from trustdesk.services.ai import AIProviderAdapter, get_ai_provider

logger = get_logger(__name__)


async def triage_ticket_service(
    db: Session,
    ticket_id: str,
    provider: AIProviderAdapter | None = None,
) -> TriageResult:
    """Orchestrate AI ticket triage, schema validation, fallback handling, and persistence.

    Enforces safe fallback:
    If the provider times out, fails, or returns malformed schema output, a safe
    fallback object is returned (category='general', priority='medium', needs_escalation=True,
    is_fallback=True), logged as an AI failure, and persisted with sanitized diagnostics.
    """
    ticket = ticket_service.get_ticket(db=db, ticket_id=ticket_id)
    active_provider = provider or get_ai_provider()

    result_schema: TriageResultSchema
    is_fallback = False

    try:
        result_schema = await active_provider.triage_ticket(
            ticket_subject=ticket.subject,
            ticket_message=ticket.message,
        )
        is_fallback = result_schema.is_fallback
    except Exception as exc:
        logger.warning(
            "AI triage execution failed; applying safe fallback",
            extra={"ticket_id": ticket_id, "error": str(exc)},
        )
        is_fallback = True
        result_schema = TriageResultSchema(
            category=TicketCategory.GENERAL,
            priority=TicketPriority.MEDIUM,
            needs_escalation=True,
            reasoning=f"AI provider classification failed ({type(exc).__name__}). Fallback classification routed to general queue with escalation.",
            is_fallback=True,
            sanitized_diagnostics={
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:200],
            },
        )

    # Persist triage outcome
    triage_record = TriageResult(
        ticket_id=ticket.ticket_id,
        category=result_schema.category.value,
        priority=result_schema.priority.value,
        needs_escalation=result_schema.needs_escalation,
        reasoning=result_schema.reasoning,
        is_fallback=is_fallback,
        sanitized_diagnostics=result_schema.sanitized_diagnostics,
    )
    db.add(triage_record)

    # Persist audit trace in PostgreSQL
    trace = ExecutionTrace(
        ticket_id=ticket.ticket_id,
        run_type="triage",
        retrieved_kb_ids=[],
        proposed_actions=[],
        executed_actions=[],
        guardrail_outcome="escalated" if result_schema.needs_escalation else "passed",
        final_status="failed" if is_fallback else "success",
        sanitized_telemetry=result_schema.sanitized_diagnostics,
    )
    db.add(trace)

    db.commit()
    db.refresh(triage_record)

    return triage_record
