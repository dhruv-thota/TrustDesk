from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from trustdesk.core.database import get_db
from trustdesk.core.security import AgentIdentity, verify_demo_token
from trustdesk.schemas.triage import TriageResultSchema
from trustdesk.services.triage_service import triage_ticket_service

router = APIRouter(prefix="/tickets", tags=["AI Triage"])


@router.post("/{ticket_id}/triage", response_model=TriageResultSchema)
async def triage_ticket_endpoint(
    ticket_id: str,
    db: Session = Depends(get_db),
    _agent: AgentIdentity = Depends(verify_demo_token),
) -> TriageResultSchema:
    """Classify ticket category, priority, and escalation need using AI triage."""
    triage_record = await triage_ticket_service(db=db, ticket_id=ticket_id)
    return TriageResultSchema.model_validate(triage_record)

