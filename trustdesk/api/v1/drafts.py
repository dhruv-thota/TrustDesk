from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from trustdesk.core.database import get_db
from trustdesk.core.logging import get_logger
from trustdesk.core.security import AgentIdentity, verify_demo_token
from trustdesk.models.ai import ExecutionTrace
from trustdesk.schemas.draft import DraftResponseSchema
from trustdesk.services.draft_service import generate_draft_service

logger = get_logger(__name__)

router = APIRouter(prefix="/tickets", tags=["Grounded Drafts"])


@router.post("/{ticket_id}/draft", response_model=DraftResponseSchema)
async def generate_draft_endpoint(
    ticket_id: str,
    db: Session = Depends(get_db),
    _agent: AgentIdentity = Depends(verify_demo_token),
) -> DraftResponseSchema:
    """Retrieve policy evidence and generate a grounded, cited customer response draft."""
    try:
        draft_response = await generate_draft_service(db=db, ticket_id=ticket_id)
        return draft_response
    except TimeoutError as exc:
        logger.warning("Draft generation provider timed out for ticket %s: %s", ticket_id, exc)
        trace = ExecutionTrace(
            ticket_id=ticket_id,
            run_type="draft_generation",
            retrieved_kb_ids=[],
            proposed_actions=[],
            executed_actions=[],
            guardrail_outcome="escalated",
            final_status="failed",
            sanitized_telemetry={"error": "AI_PROVIDER_TIMEOUT", "detail": str(exc)},
        )
        db.add(trace)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The upstream AI provider timed out after 15 seconds.",
        ) from exc
    except Exception as exc:
        # Check if it's a domain exception (e.g. TicketNotFoundError)
        if hasattr(exc, "status_code"):
            raise exc
        logger.error("Draft generation upstream failure for ticket %s: %s", ticket_id, exc)
        trace = ExecutionTrace(
            ticket_id=ticket_id,
            run_type="draft_generation",
            retrieved_kb_ids=[],
            proposed_actions=[],
            executed_actions=[],
            guardrail_outcome="escalated",
            final_status="failed",
            sanitized_telemetry={"error": "AI_PROVIDER_FAILURE", "detail": str(exc)[:200]},
        )
        db.add(trace)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"The upstream AI provider returned an error: {type(exc).__name__}",
        ) from exc

