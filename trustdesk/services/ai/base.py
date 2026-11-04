from __future__ import annotations

from abc import ABC, abstractmethod

from trustdesk.schemas.draft import ActionRecommendationSchema, DraftResponseSchema
from trustdesk.schemas.ticket import TicketContextSchema
from trustdesk.schemas.triage import TriageResultSchema
from trustdesk.services.retrieval.base import PolicySectionMatch


class AIProviderAdapter(ABC):
    """Abstract interface decoupling business services from specific LLM providers."""

    @abstractmethod
    async def triage_ticket(
        self,
        ticket_subject: str,
        ticket_message: str,
    ) -> TriageResultSchema:
        """Classify ticket into category, priority, and escalation need."""
        pass

    @abstractmethod
    async def generate_draft(
        self,
        ticket_context: TicketContextSchema,
        evidence: list[PolicySectionMatch],
    ) -> DraftResponseSchema:
        """Generate response draft with citations grounded in retrieved evidence."""
        pass

    @abstractmethod
    async def evaluate_action_recommendation(
        self,
        ticket_context: TicketContextSchema,
        evidence: list[PolicySectionMatch],
    ) -> ActionRecommendationSchema:
        """Evaluate context and policy evidence to propose an advisory action recommendation.

        NOTE: Output is strictly advisory with ZERO execution rights.
        """
        pass

