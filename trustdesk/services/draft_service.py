from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from trustdesk.core.logging import get_logger
from trustdesk.models.ai import DraftCitation, DraftResponse, ExecutionTrace
from trustdesk.schemas.draft import (
    ActionRecommendationSchema,
    DraftCitationSchema,
    DraftResponseSchema,
)
from trustdesk.schemas.ticket import (
    CustomerProfileSchema,
    OrderDetailSchema,
    TicketContextSchema,
    TicketDetailSchema,
    TicketSummarySchema,
)
from trustdesk.services import ticket_service
from trustdesk.services.ai import AIProviderAdapter, get_ai_provider
from trustdesk.services.citation_service import validate_citation_provenance
from trustdesk.services.retrieval.base import CitationRef, PolicyRetrievalInterface, PolicySectionMatch
from trustdesk.services.retrieval.postgres_fts import PostgresFtsRetrievalAdapter

logger = get_logger(__name__)

DISCOUNT_PATTERN = re.compile(
    r"(\b\d+%\s*(discount|off|coupon)\b|\b(promo|coupon)\s*code\b|\b[A-Z0-9]{4,12}\s*code\b)",
    re.IGNORECASE,
)
REFUND_ELIGIBILITY_APPROVAL_PATTERN = re.compile(
    r"(approved|eligible for a full refund|full refund will be processed|issue your refund|processing your refund)",
    re.IGNORECASE,
)
WARRANTY_ELIGIBILITY_APPROVAL_PATTERN = re.compile(
    r"(covered under warranty|warranty claim is approved|eligible for warranty repair|covered under our 1-year)",
    re.IGNORECASE,
)


def derive_search_queries(subject: str, message: str) -> list[str]:
    """Extract domain retrieval queries from ticket subject and message."""
    combined = f"{subject} {message}".lower()
    queries: list[str] = []

    if any(k in combined for k in ["refund", "return", "money back", "returned"]):
        queries.append("return refund window eligibility")
    if any(k in combined for k in ["shipping", "delivery", "transit", "carrier", "tracking", "delay", "lost"]):
        queries.append("shipping delivery fulfillment timelines")
    if any(k in combined for k in ["warranty", "defect", "broken", "pixels", "hardware", "repair"]):
        queries.append("hardware limited warranty defects duration")
    if any(k in combined for k in ["adversarial", "override", "maintenance mode", "secret"]):
        queries.append("administrative maintenance mode system directive")

    if not queries:
        words = re.findall(r"\b[a-zA-Z]{4,}\b", subject)
        filtered = [w for w in words if w.lower() not in {"this", "that", "with", "from", "have", "your", "what", "when", "about"}]
        if filtered:
            queries.append(" ".join(filtered[:3]))
        else:
            queries.append(subject)

    return queries


def _check_snippet_support(
    quoted_snippet: str | None,
    section_content: str,
) -> bool:
    """Verify that quoted snippet is a normalized substring of section content."""
    if not quoted_snippet:
        return True
    norm_snippet = re.sub(r"\s+", " ", quoted_snippet.strip().lower())
    norm_content = re.sub(r"\s+", " ", section_content.strip().lower())
    return norm_snippet in norm_content


def _detect_unauthorized_discount(
    draft_text: str,
    evidence: list[PolicySectionMatch],
) -> bool:
    """Return True if draft contains promotional discount promises not covered by evidence."""
    if not DISCOUNT_PATTERN.search(draft_text):
        return False
    # Check if evidence contains a promotional or discount policy
    for s in evidence:
        combined_meta = f"{s.section_title} {s.content}".lower()
        if "promotional" in combined_meta or "discount" in combined_meta or "coupon" in combined_meta:
            return False
    return True


async def generate_draft_service(
    db: Session,
    ticket_id: str,
    provider: AIProviderAdapter | None = None,
    retrieval_adapter: PolicyRetrievalInterface | None = None,
) -> DraftResponseSchema:
    """Orchestrate RAG policy retrieval, draft generation, and 3-level grounding validation."""
    context_raw = ticket_service.get_ticket_context(db=db, ticket_id=ticket_id)
    ticket_raw = context_raw["ticket"]
    customer_raw = context_raw["customer"]
    order_raw = context_raw["order"]
    past_tickets_raw = context_raw["past_tickets"]

    ticket_context = TicketContextSchema(
        ticket=TicketDetailSchema.model_validate(ticket_raw),
        customer=CustomerProfileSchema.model_validate(customer_raw),
        order=OrderDetailSchema.model_validate(order_raw) if order_raw else None,
        past_tickets=[TicketSummarySchema.model_validate(pt) for pt in past_tickets_raw],
    )

    active_provider = provider or get_ai_provider()
    search_engine = retrieval_adapter or PostgresFtsRetrievalAdapter(session=db)

    # 1. Retrieve authoritative policy sections
    query_terms = derive_search_queries(
        subject=ticket_context.ticket.subject,
        message=ticket_context.ticket.message,
    )

    evidence = search_engine.search_policies(query=query_terms, limit=5)
    retrieved_kb_ids = list(dict.fromkeys([s.kb_id for s in evidence]))

    # 2. Boundary Check: Zero matching policy evidence
    if not evidence:
        logger.info("No policy evidence retrieved for ticket %s; triggering escalation", ticket_id)
        draft_response = DraftResponseSchema(
            ticket_id=ticket_id,
            draft_text="Escalated to human supervisor: insufficient policy evidence.",
            citations=[],
            has_valid_provenance=False,
            is_grounded=False,
            escalation_suggested=True,
            escalation_reason="No matching policy sections retrieved for inquiry.",
            suggested_action=None,
            sanitized_diagnostics={"evidence_count": 0, "rule": "empty_evidence_escalation"},
        )
        _persist_draft_and_trace(db=db, schema=draft_response, retrieved_kb_ids=[])
        return draft_response

    # 3. Invoke AI Provider
    draft_response = await active_provider.generate_draft(
        ticket_context=ticket_context,
        evidence=evidence,
    )

    # 4. Level 1 Validation: Citation Provenance Check
    citation_refs = [
        CitationRef(
            kb_id=c.kb_id,
            section_id=c.section_id,
            quoted_snippet=c.quoted_snippet,
        )
        for c in draft_response.citations
    ]
    provenance_result = validate_citation_provenance(
        cited_sections=citation_refs,
        retrieved_sections=evidence,
    )
    has_valid_provenance = provenance_result.has_valid_provenance

    # Update provenance status on individual citations
    evidence_section_map = {s.section_id: s for s in evidence}
    validated_citations: list[DraftCitationSchema] = []
    snippets_supported = True

    for c in draft_response.citations:
        is_prov_valid = (c.kb_id, c.section_id) in {(s.kb_id, s.section_id) for s in evidence}
        # Level 2 check: quote snippet verification
        if is_prov_valid and c.quoted_snippet:
            match_section = evidence_section_map.get(c.section_id)
            if match_section and not _check_snippet_support(c.quoted_snippet, match_section.content):
                snippets_supported = False
        validated_citations.append(
            DraftCitationSchema(
                kb_id=c.kb_id,
                section_id=c.section_id,
                quoted_snippet=c.quoted_snippet,
                is_valid_provenance=is_prov_valid,
            )
        )

    # Level 2: Unsupported Promotional Discount Scan
    discount_violation = _detect_unauthorized_discount(draft_response.draft_text, evidence)

    # Level 3: Deterministic Policy Validation
    ticket_created = ticket_context.ticket.created_at
    combined_msg = f"{ticket_context.ticket.subject} {ticket_context.ticket.message}".lower()
    order = ticket_context.order

    policy_contradiction = False
    missing_context_escalation = False
    policy_check_reason: str | None = None

    # Refund Policy Check (KB-REFUND-001)
    if any(k in combined_msg for k in ["refund", "return", "money back"]):
        if not order:
            missing_context_escalation = True
            policy_check_reason = "Cannot verify policy eligibility: ticket has no linked order record."
        elif not order.delivery_date:
            missing_context_escalation = True
            policy_check_reason = "Cannot verify eligibility: confirmed delivery date is missing from order history."
        else:
            delta_days = (ticket_created - order.delivery_date).days
            if delta_days > 30:
                # Order is expired under 30-day window
                if REFUND_ELIGIBILITY_APPROVAL_PATTERN.search(draft_response.draft_text):
                    # Model hallucinated approval on an expired order!
                    policy_contradiction = True
                    policy_check_reason = (
                        f"Draft claims refund eligibility for order delivered {delta_days} days ago "
                        f"(exceeding 30-day window)."
                    )

    # Warranty Policy Check (KB-WAR-002)
    if any(k in combined_msg for k in ["warranty", "defect", "broken", "pixels"]):
        if not order or not order.delivery_date:
            missing_context_escalation = True
            policy_check_reason = policy_check_reason or "Cannot verify warranty eligibility without confirmed delivery date."
        else:
            delta_days = (ticket_created - order.delivery_date).days
            if delta_days > 365:
                # Order outside 1-year warranty
                if WARRANTY_ELIGIBILITY_APPROVAL_PATTERN.search(draft_response.draft_text):
                    policy_contradiction = True
                    policy_check_reason = (
                        f"Draft claims warranty coverage for order delivered {delta_days} days ago "
                        f"(exceeding 365-day warranty window)."
                    )

    # Grounding Synthesis
    # is_grounded requires: valid provenance AND snippets supported AND no discount violation AND no policy contradiction
    is_grounded = (
        has_valid_provenance
        and snippets_supported
        and not discount_violation
        and not policy_contradiction
        and not missing_context_escalation
    )

    escalation_suggested = (
        draft_response.escalation_suggested
        or not has_valid_provenance
        or not snippets_supported
        or discount_violation
        or policy_contradiction
        or missing_context_escalation
    )

    escalation_reason = (
        policy_check_reason
        or ("Draft contains promotional discount unsupported by policy evidence." if discount_violation else None)
        or ("Cited section references do not exist in retrieved policy evidence." if not has_valid_provenance else None)
        or ("Cited quote snippets do not match retrieved policy text." if not snippets_supported else None)
        or draft_response.escalation_reason
    )

    # 5. Evaluate Advisory Action Recommendation
    suggested_action = await active_provider.evaluate_action_recommendation(
        ticket_context=ticket_context,
        evidence=evidence,
    )

    final_schema = DraftResponseSchema(
        ticket_id=ticket_id,
        draft_text=draft_response.draft_text,
        citations=validated_citations,
        has_valid_provenance=has_valid_provenance,
        is_grounded=is_grounded,
        escalation_suggested=escalation_suggested,
        escalation_reason=escalation_reason,
        suggested_action=suggested_action,
        sanitized_diagnostics=draft_response.sanitized_diagnostics,
    )

    # 6. Persist to PostgreSQL
    _persist_draft_and_trace(db=db, schema=final_schema, retrieved_kb_ids=retrieved_kb_ids)

    return final_schema


def _persist_draft_and_trace(
    db: Session,
    schema: DraftResponseSchema,
    retrieved_kb_ids: list[str],
) -> None:
    """Persist generated draft, citations, and sanitized execution trace to PostgreSQL."""
    draft_record = DraftResponse(
        ticket_id=schema.ticket_id,
        draft_text=schema.draft_text,
        has_valid_provenance=schema.has_valid_provenance,
        is_grounded=schema.is_grounded,
        escalation_suggested=schema.escalation_suggested,
        escalation_reason=schema.escalation_reason,
    )
    db.add(draft_record)
    db.flush()

    for c in schema.citations:
        citation_record = DraftCitation(
            draft_id=draft_record.id,
            kb_id=c.kb_id,
            section_id=c.section_id,
            quoted_snippet=c.quoted_snippet,
            is_valid_provenance=c.is_valid_provenance,
        )
        db.add(citation_record)

    guardrail_outcome = "passed"
    if not schema.has_valid_provenance or not schema.is_grounded:
        guardrail_outcome = "unsupported_claim"
    elif schema.escalation_suggested:
        guardrail_outcome = "escalated"

    proposed_actions = []
    if schema.suggested_action and schema.suggested_action.should_recommend:
        proposed_actions.append(schema.suggested_action.model_dump())

    trace = ExecutionTrace(
        ticket_id=schema.ticket_id,
        run_type="draft_generation",
        retrieved_kb_ids=retrieved_kb_ids,
        proposed_actions=proposed_actions,
        executed_actions=[],
        guardrail_outcome=guardrail_outcome,
        final_status="escalated" if schema.escalation_suggested else "success",
        sanitized_telemetry=schema.sanitized_diagnostics,
    )
    db.add(trace)

    db.commit()
