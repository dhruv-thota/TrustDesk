from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from trustdesk.schemas.draft import (
    ActionRecommendationSchema,
    DraftCitationSchema,
    DraftResponseSchema,
)
from trustdesk.schemas.ticket import TicketContextSchema
from trustdesk.schemas.triage import (
    TicketCategory,
    TicketPriority,
    TriageResultSchema,
)
from trustdesk.services.ai.base import AIProviderAdapter
from trustdesk.services.retrieval.base import PolicySectionMatch


class MockAIProvider(AIProviderAdapter):
    """Deterministic, zero-network mock provider for repeatable testing."""

    async def triage_ticket(
        self,
        ticket_subject: str,
        ticket_message: str,
    ) -> TriageResultSchema:
        combined = f"{ticket_subject} {ticket_message}".lower()

        # Simulated failure modes
        if "simulate_timeout" in combined:
            raise TimeoutError("Mock provider simulated timeout after 15s")
        if "simulate_malformed" in combined:
            raise ValueError("Mock provider returned unparseable malformed output")

        # Distress / legal escalation keywords
        is_distress = any(k in combined for k in ["lawyer", "legal action", "sue", "attorney", "unacceptable"])

        # Security classification
        if any(k in combined for k in ["password", "hacked", "takeover", "unauthorized access", "breach", "security"]):
            return TriageResultSchema(
                category=TicketCategory.ACCOUNT_SECURITY,
                priority=TicketPriority.URGENT,
                needs_escalation=True,
                reasoning="Inquiry involves credential security or suspected account takeover.",
                is_fallback=False,
                sanitized_diagnostics={"provider": "mock", "rule": "security_keyword"},
            )

        # Refund classification
        if any(k in combined for k in ["refund", "return", "money back", "returned"]):
            priority = TicketPriority.URGENT if is_distress else TicketPriority.HIGH
            return TriageResultSchema(
                category=TicketCategory.REFUND,
                priority=priority,
                needs_escalation=is_distress,
                reasoning="Customer is inquiring about return eligibility or refund processing.",
                is_fallback=False,
                sanitized_diagnostics={"provider": "mock", "rule": "refund_keyword"},
            )

        # Warranty classification
        if any(k in combined for k in ["warranty", "defect", "broken", "repair", "pixels", "faulty", "hardware"]):
            priority = TicketPriority.HIGH if is_distress else TicketPriority.MEDIUM
            return TriageResultSchema(
                category=TicketCategory.WARRANTY,
                priority=priority,
                needs_escalation=is_distress,
                reasoning="Inquiry describes hardware issues or warranty claim questions.",
                is_fallback=False,
                sanitized_diagnostics={"provider": "mock", "rule": "warranty_keyword"},
            )

        # Shipping classification
        if any(k in combined for k in ["shipping", "delivery", "track", "package", "transit", "carrier", "lost"]):
            priority = TicketPriority.HIGH if is_distress else TicketPriority.MEDIUM
            return TriageResultSchema(
                category=TicketCategory.SHIPPING,
                priority=priority,
                needs_escalation=is_distress,
                reasoning="Inquiry relates to fulfillment timelines or shipment tracking.",
                is_fallback=False,
                sanitized_diagnostics={"provider": "mock", "rule": "shipping_keyword"},
            )

        # Billing classification
        if any(k in combined for k in ["billing", "charge", "invoice", "payment", "overcharge", "card"]):
            priority = TicketPriority.HIGH if is_distress else TicketPriority.MEDIUM
            return TriageResultSchema(
                category=TicketCategory.BILLING,
                priority=priority,
                needs_escalation=is_distress,
                reasoning="Inquiry relates to billing disputes, invoices, or charges.",
                is_fallback=False,
                sanitized_diagnostics={"provider": "mock", "rule": "billing_keyword"},
            )

        # General inquiry fallback
        return TriageResultSchema(
            category=TicketCategory.GENERAL,
            priority=TicketPriority.LOW,
            needs_escalation=is_distress,
            reasoning="General support inquiry without critical keywords.",
            is_fallback=False,
            sanitized_diagnostics={"provider": "mock", "rule": "general_default"},
        )

    async def generate_draft(
        self,
        ticket_context: TicketContextSchema,
        evidence: list[PolicySectionMatch],
    ) -> DraftResponseSchema:
        combined = f"{ticket_context.ticket.subject} {ticket_context.ticket.message}".lower()

        # Simulated failure modes
        if "simulate_timeout" in combined:
            raise TimeoutError("Mock provider simulated timeout after 15s")
        if "simulate_malformed" in combined:
            raise ValueError("Mock provider returned unparseable malformed output")

        # Simulated unauthorized discount test
        if "simulate_unauthorized_discount" in combined:
            citations: list[DraftCitationSchema] = []
            if evidence:
                first = evidence[0]
                citations.append(
                    DraftCitationSchema(
                        kb_id=first.kb_id,
                        section_id=first.section_id,
                        quoted_snippet=first.content[:80] if len(first.content) >= 80 else first.content,
                        is_valid_provenance=True,
                    )
                )
            return DraftResponseSchema(
                ticket_id=ticket_context.ticket.ticket_id,
                draft_text="Thank you for reaching out! We are delighted to offer you a 25% discount coupon on your next order: PROMO25.",
                citations=citations,
                has_valid_provenance=True,
                is_grounded=False,
                escalation_suggested=True,
                escalation_reason="Draft contains promotional discount unsupported by evidence.",
                sanitized_diagnostics={"provider": "mock", "simulated": "unauthorized_discount"},
            )

        # Simulated hallucinated citation test
        if "simulate_hallucinated_citation" in combined:
            return DraftResponseSchema(
                ticket_id=ticket_context.ticket.ticket_id,
                draft_text="Your return is processed according to our policy clause.",
                citations=[
                    DraftCitationSchema(
                        kb_id="KB-REFUND-001",
                        section_id="KB-REFUND-001#sec-99",
                        quoted_snippet="Non-existent snippet",
                        is_valid_provenance=False,
                    )
                ],
                has_valid_provenance=False,
                is_grounded=False,
                escalation_suggested=True,
                escalation_reason="Draft cited an unretrieved policy section reference.",
                sanitized_diagnostics={"provider": "mock", "simulated": "hallucinated_citation"},
            )

        # Insufficient evidence
        if not evidence:
            return DraftResponseSchema(
                ticket_id=ticket_context.ticket.ticket_id,
                draft_text="Escalated to human supervisor: insufficient policy evidence.",
                citations=[],
                has_valid_provenance=False,
                is_grounded=False,
                escalation_suggested=True,
                escalation_reason="No matching policy sections retrieved for inquiry.",
                sanitized_diagnostics={"provider": "mock", "evidence_count": 0},
            )

        # Identify relevant policy evidence
        refund_sec = next((s for s in evidence if s.kb_id == "KB-REFUND-001"), None)
        war_sec = next((s for s in evidence if s.kb_id == "KB-WAR-002"), None)
        shipping_sec = next((s for s in evidence if s.kb_id == "KB-SHIPPING-001"), None)

        citations = []
        is_grounded = True
        escalation_suggested = False
        escalation_reason = None
        draft_text = ""

        order = ticket_context.order
        ticket_created = ticket_context.ticket.created_at

        # Refund inquiry draft synthesis
        if refund_sec and any(k in combined for k in ["refund", "return", "money back"]):
            snippet = "Customers may return eligible hardware products within 30 calendar days from the date of confirmed delivery."
            citations.append(
                DraftCitationSchema(
                    kb_id=refund_sec.kb_id,
                    section_id=refund_sec.section_id,
                    quoted_snippet=snippet,
                    is_valid_provenance=True,
                )
            )

            # Simulated hallucinated eligibility on expired order
            if "simulate_hallucinated_eligibility" in combined:
                draft_text = (
                    "Thank you for contacting us. We are pleased to confirm that your return request has been approved, "
                    "and a full refund will be processed to your original payment method under our Standard Return and Refund Policy."
                )
                # Level 3 will override is_grounded to False in draft_service, but mock reflects the LLM's claim:
                return DraftResponseSchema(
                    ticket_id=ticket_context.ticket.ticket_id,
                    draft_text=draft_text,
                    citations=citations,
                    has_valid_provenance=True,
                    is_grounded=True,  # LLM claims grounded, draft_service verifies
                    escalation_suggested=False,
                    sanitized_diagnostics={"provider": "mock", "simulated": "hallucinated_eligibility"},
                )

            if not order or not order.delivery_date:
                draft_text = (
                    "Thank you for reaching out regarding your return inquiry. According to our policy, returns are eligible "
                    "within 30 calendar days of confirmed delivery. However, we cannot verify your delivery date from your record. "
                    "I have escalated your request to a supervisor for verification."
                )
                escalation_suggested = True
                is_grounded = False
                escalation_reason = "Order delivery date missing or order unlinked."
            else:
                delivery_date = order.delivery_date
                delta_days = (ticket_created - delivery_date).days
                if delta_days <= 30:
                    draft_text = (
                        f"Thank you for contacting TrustDesk support. Your order {order.order_id} was delivered on "
                        f"{delivery_date.strftime('%Y-%m-%d')}, which is within our 30-day return window. "
                        f"We are glad to initiate the return process under our Standard Return Policy."
                    )
                    is_grounded = True
                    escalation_suggested = False
                else:
                    draft_text = (
                        f"Thank you for reaching out to TrustDesk support. Under our Standard Return and Refund Policy, "
                        f"items must be returned within 30 calendar days of delivery. Because your order {order.order_id} was "
                        f"delivered on {delivery_date.strftime('%Y-%m-%d')} ({delta_days} days prior to this inquiry), "
                        f"it is outside the eligible return window."
                    )
                    # Grounded ineligibility
                    is_grounded = True
                    escalation_suggested = False

        # Warranty inquiry draft synthesis
        elif war_sec and any(k in combined for k in ["warranty", "defect", "broken", "pixels"]):
            snippet = "All electronic hardware devices purchased through authorized channels include a 1-year (365 calendar days) limited manufacturer warranty starting from the confirmed date of delivery."
            citations.append(
                DraftCitationSchema(
                    kb_id=war_sec.kb_id,
                    section_id=war_sec.section_id,
                    quoted_snippet=snippet,
                    is_valid_provenance=True,
                )
            )
            if not order or not order.delivery_date:
                draft_text = "Thank you for contacting us regarding warranty service. We need to verify your confirmed delivery date to process this claim."
                escalation_suggested = True
                is_grounded = False
                escalation_reason = "Cannot verify warranty window without confirmed delivery date."
            else:
                delta_days = (ticket_created - order.delivery_date).days
                if delta_days <= 365:
                    draft_text = (
                        f"Thank you for reporting this issue. Your hardware is covered under our 1-year limited manufacturer warranty. "
                        f"We will be happy to assist you with warranty service."
                    )
                    is_grounded = True
                else:
                    draft_text = f"Thank you for contacting us. Your order was delivered {delta_days} days ago, which is outside the 1-year warranty coverage window."
                    is_grounded = True

        # Shipping inquiry draft synthesis
        elif shipping_sec:
            snippet = "Standard shipping orders are dispatched within 1 to 2 business days from order placement."
            citations.append(
                DraftCitationSchema(
                    kb_id=shipping_sec.kb_id,
                    section_id=shipping_sec.section_id,
                    quoted_snippet=snippet,
                    is_valid_provenance=True,
                )
            )
            draft_text = "Thank you for inquiring about your shipment. Standard orders are dispatched within 1 to 2 business days and delivered in 3 to 5 business days."
            is_grounded = True

        else:
            first = evidence[0]
            citations.append(
                DraftCitationSchema(
                    kb_id=first.kb_id,
                    section_id=first.section_id,
                    quoted_snippet=first.content[:60] if len(first.content) >= 60 else first.content,
                    is_valid_provenance=True,
                )
            )
            draft_text = f"Thank you for your inquiry. According to our {first.section_title}, we are reviewing your request."
            is_grounded = True

        return DraftResponseSchema(
            ticket_id=ticket_context.ticket.ticket_id,
            draft_text=draft_text,
            citations=citations,
            has_valid_provenance=True,
            is_grounded=is_grounded,
            escalation_suggested=escalation_suggested,
            escalation_reason=escalation_reason,
            sanitized_diagnostics={"provider": "mock", "evidence_count": len(evidence)},
        )

    async def evaluate_action_recommendation(
        self,
        ticket_context: TicketContextSchema,
        evidence: list[PolicySectionMatch],
    ) -> ActionRecommendationSchema:
        combined = f"{ticket_context.ticket.subject} {ticket_context.ticket.message}".lower()

        # Check if refund-related
        is_refund_inquiry = any(k in combined for k in ["refund", "return", "money back"])
        order = ticket_context.order

        if is_refund_inquiry and order and order.delivery_date:
            delta_days = (ticket_context.ticket.created_at - order.delivery_date).days
            if delta_days <= 30:
                return ActionRecommendationSchema(
                    action_type="start_refund_review",
                    should_recommend=True,
                    payload={
                        "order_id": order.order_id,
                        "customer_id": ticket_context.customer.customer_id,
                        "reason": "customer_return_request_within_window",
                        "days_since_delivery": delta_days,
                    },
                    reasoning=f"Order {order.order_id} delivered {delta_days} days ago (within 30-day window). Recommend starting refund review for agent approval.",
                )
            else:
                return ActionRecommendationSchema(
                    action_type="start_refund_review",
                    should_recommend=False,
                    payload={"order_id": order.order_id, "days_since_delivery": delta_days},
                    reasoning=f"Order delivery was {delta_days} days ago, exceeding the 30-day policy return window. Refund review not recommended.",
                )

        if is_refund_inquiry and (not order or not order.delivery_date):
            return ActionRecommendationSchema(
                action_type="start_refund_review",
                should_recommend=False,
                payload={},
                reasoning="Cannot recommend refund review: linked order or delivery date missing.",
            )

        return ActionRecommendationSchema(
            action_type="start_refund_review",
            should_recommend=False,
            payload={},
            reasoning="Inquiry is not refund-related. No action recommended.",
        )

