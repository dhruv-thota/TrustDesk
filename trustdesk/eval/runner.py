from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from trustdesk.core.database import get_db_session
from trustdesk.core.logging import configure_logging, get_logger
from trustdesk.eval.loader import (
    DatasetEmptyError,
    DatasetNotFoundError,
    DatasetPathSecurityError,
    DatasetUnreadableError,
    DatasetValidationError,
    DuplicateCaseIDError,
    load_and_validate_dataset,
)
from trustdesk.eval.metrics import calculate_metrics, score_case_outcome
from trustdesk.models.eval import EvalResult, EvalRun
from trustdesk.models.knowledge import KBSection
from trustdesk.schemas.draft import ActionRecommendationSchema, DraftResponseSchema
from trustdesk.schemas.eval import (
    CaseEvaluationOutcome,
    EvaluationCaseSchema,
    MetricsSummary,
    ValidatedLine,
)
from trustdesk.schemas.ticket import TicketContextSchema
from trustdesk.services.ai import AIProviderAdapter, get_ai_provider
from trustdesk.services.citation_service import validate_citation_provenance
from trustdesk.services.draft_service import (
    REFUND_ELIGIBILITY_APPROVAL_PATTERN,
    WARRANTY_ELIGIBILITY_APPROVAL_PATTERN,
    _check_snippet_support,
    _detect_unauthorized_discount,
    derive_search_queries,
)
from trustdesk.services.retrieval.base import CitationRef, PolicyRetrievalInterface, PolicySectionMatch
from trustdesk.services.retrieval.postgres_fts import PostgresFtsRetrievalAdapter

logger = get_logger(__name__)

# Sanitization regex patterns for PII and secrets
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
API_KEY_PATTERN = re.compile(r"\b(AIza[0-9A-Za-z-_]{35}|SECRET-[A-Za-z0-9-_]+)\b")
SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|auth|authorization|credential)"
)


class ActiveEvaluationAlreadyRunningError(Exception):
    """Raised when an evaluation run is attempted while another is queued or running."""
    pass


class RunAlreadyCompletedError(Exception):
    """Raised when attempting to execute an evaluation run that has already completed."""
    pass


class RunAlreadyFailedError(Exception):
    """Raised when attempting to restart an evaluation run that has already failed."""
    pass


def sanitize_text(text: str | None) -> str:
    """Mask email addresses, credit cards, and API secrets from output text."""
    if not text:
        return ""
    masked = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    masked = CARD_PATTERN.sub("[REDACTED_CARD]", masked)
    masked = API_KEY_PATTERN.sub("[REDACTED_SECRET]", masked)
    return masked


def sanitize_value(value: Any, depth: int = 0, max_depth: int = 5) -> Any:
    """Recursively sanitize arbitrary objects, nested dicts, and lists with depth bounding."""
    if depth > max_depth:
        return "[TRUNCATED_DEPTH]"

    if value is None or isinstance(value, (int, float, bool)):
        return value

    if isinstance(value, str):
        if len(value) > 4000:
            value = value[:4000] + "...[TRUNCATED_LENGTH]"
        return sanitize_text(value)

    if isinstance(value, dict):
        sanitized_dict: dict[str, Any] = {}
        for k, v in value.items():
            key_str = str(k)
            sanitized_key = sanitize_text(key_str)
            if SENSITIVE_KEY_PATTERN.search(key_str):
                sanitized_dict[sanitized_key] = "[REDACTED_SECRET]"
            else:
                sanitized_dict[sanitized_key] = sanitize_value(v, depth=depth + 1, max_depth=max_depth)
        return sanitized_dict

    if isinstance(value, (list, tuple, set)):
        items = list(value)
        if len(items) > 50:
            items = items[:50]
        return [sanitize_value(item, depth=depth + 1, max_depth=max_depth) for item in items]

    # Non-primitive, non-collection objects (e.g. custom classes, exceptions)
    str_val = str(value)
    if len(str_val) > 200:
        str_val = str_val[:200] + "...[TRUNCATED]"
    return sanitize_text(str_val)


def sanitize_diagnostics(diagnostics: dict[str, Any]) -> dict[str, Any]:
    """Sanitize execution diagnostics dictionary recursively."""
    sanitized = sanitize_value(diagnostics, depth=0)
    return sanitized if isinstance(sanitized, dict) else {"details": sanitized}


class EvaluationRunner:
    """Standalone evaluation suite execution engine."""

    def __init__(
        self,
        session: Session | None = None,
        provider: AIProviderAdapter | None = None,
        retrieval_adapter: PolicyRetrievalInterface | None = None,
    ) -> None:
        self._session = session
        self._provider = provider
        self._retrieval_adapter = retrieval_adapter

    async def run(
        self,
        dataset_path: str | Path,
        run_id: uuid.UUID | None = None,
        job_id: str | None = None,
        enforce_containment: bool = False,
    ) -> EvalRun:
        """Execute evaluation run over a JSONL dataset file.

        1. Creates durable EvalRun record in PostgreSQL with status='running'.
        2. Validates dataset pre-flight. Fatal failures immediately mark run as 'failed'.
        3. Executes case-by-case pipeline using approved AI provider and RAG retrieval.
        4. Validates citation provenance, policy grounding, guardrails, and action recommendations.
        5. Persists per-case EvalResult rows with idempotent upsert.
        6. Computes aggregate metrics and enforces complete input accounting.
        7. Transitions run to 'completed' and commits.
        """
        active_run_id = run_id or uuid.uuid4()
        active_job_id = job_id or f"eval-job-{active_run_id.hex[:12]}"
        path = Path(dataset_path).resolve()

        if self._session:
            return await self._run_in_session(
                session=self._session,
                dataset_path=path,
                run_id=active_run_id,
                job_id=active_job_id,
                enforce_containment=enforce_containment,
            )
        else:
            with get_db_session() as session:
                return await self._run_in_session(
                    session=session,
                    dataset_path=path,
                    run_id=active_run_id,
                    job_id=active_job_id,
                    enforce_containment=enforce_containment,
                )

    async def _run_in_session(
        self,
        session: Session,
        dataset_path: Path,
        run_id: uuid.UUID,
        job_id: str,
        enforce_containment: bool = False,
    ) -> EvalRun:
        now_utc = datetime.now(timezone.utc)

        # 1. Resolve or Initialize run record (Enforces idx_single_active_eval_run and lifecycle)
        existing_run = session.execute(
            select(EvalRun).where(EvalRun.run_id == run_id).with_for_update()
        ).scalar_one_or_none()

        if existing_run:
            if existing_run.status == "completed":
                raise RunAlreadyCompletedError(
                    f"Evaluation run {run_id} is already completed and cannot be re-executed."
                )
            if existing_run.status == "failed":
                raise RunAlreadyFailedError(
                    f"Evaluation run {run_id} has already failed and cannot be restarted."
                )
            if existing_run.status == "running":
                raise ActiveEvaluationAlreadyRunningError(
                    f"Evaluation run {run_id} is already running."
                )
            if existing_run.status == "queued":
                # Atomically claim the queued record for this worker
                existing_run.status = "running"
                existing_run.started_at = now_utc
                eval_run = existing_run
                session.commit()
            else:
                raise ActiveEvaluationAlreadyRunningError(
                    f"Evaluation run {run_id} has unsupported active status '{existing_run.status}'."
                )
        else:
            # Standalone / CLI run: create new EvalRun record (Enforces idx_single_active_eval_run)
            eval_run = EvalRun(
                run_id=run_id,
                job_id=job_id,
                status="running",
                total_cases=0,
                passed_cases=0,
                metrics_summary={},
                error_details=None,
                created_at=now_utc,
                started_at=now_utc,
                finished_at=None,
            )
            session.add(eval_run)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                msg = f"Cannot start evaluation run: another active run is currently queued or running ({exc})"
                logger.warning(msg)
                raise ActiveEvaluationAlreadyRunningError(msg) from exc

        # 2. Check Knowledge Base readiness (Section 8: KB Readiness)
        kb_section_count = session.scalar(select(func.count()).select_from(KBSection))
        if not kb_section_count or kb_section_count < 9:
            logger.error("Knowledge base policy sections are not indexed (count=%s)", kb_section_count)
            empty_summary = calculate_metrics([])
            eval_run.status = "failed"
            eval_run.finished_at = datetime.now(timezone.utc)
            eval_run.error_details = {
                "error_code": "KB_SECTIONS_UNAVAILABLE",
                "message": (
                    f"Required knowledge base policy sections are not indexed in PostgreSQL "
                    f"(found {kb_section_count or 0}, expected >= 9). Ingestion must be completed before evaluation."
                ),
            }
            eval_run.metrics_summary = empty_summary.model_dump()
            session.commit()
            return eval_run

        # 3. Pre-flight dataset validation
        try:
            dataset_result = load_and_validate_dataset(
                dataset_path,
                raise_on_fatal=True,
                enforce_containment=enforce_containment,
            )
        except DatasetValidationError as exc:
            logger.error("Pre-flight dataset validation failed: %s", exc)
            empty_summary = calculate_metrics([])
            eval_run.status = "failed"
            eval_run.finished_at = datetime.now(timezone.utc)
            eval_run.error_details = {
                "error_code": "DATASET_VALIDATION_ERROR",
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
            eval_run.metrics_summary = empty_summary.model_dump()
            session.commit()
            return eval_run

        provider = self._provider or get_ai_provider()
        retrieval = self._retrieval_adapter or PostgresFtsRetrievalAdapter(session=session)

        # 3. Case-by-case execution
        case_outcomes: list[CaseEvaluationOutcome] = []

        for validated_line in dataset_result.lines:
            outcome = await self._execute_line(
                session=session,
                run_id=run_id,
                line=validated_line,
                provider=provider,
                retrieval=retrieval,
            )
            case_outcomes.append(outcome)
            self._upsert_eval_result(session=session, run_id=run_id, outcome=outcome)

        # 4. Metrics & Input Accounting calculation
        summary = calculate_metrics(case_outcomes)

        # 5. Complete input accounting invariant check
        if not summary.input_accounting.is_valid:
            eval_run.status = "failed"
            eval_run.finished_at = datetime.now(timezone.utc)
            eval_run.error_details = {
                "error_code": "INPUT_ACCOUNTING_INVARIANT_VIOLATION",
                "message": (
                    f"Total lines ({summary.input_accounting.total_lines}) != "
                    f"evaluated ({summary.input_accounting.evaluated}) + "
                    f"inconclusive ({summary.input_accounting.inconclusive}) + "
                    f"invalid_input ({summary.input_accounting.invalid_input}) + "
                    f"model_failure ({summary.input_accounting.model_failure})"
                ),
            }
            eval_run.metrics_summary = summary.model_dump()
            session.commit()
            return eval_run

        # 6. Complete and commit run
        eval_run.status = "completed"
        eval_run.finished_at = datetime.now(timezone.utc)
        eval_run.total_cases = summary.total_cases
        eval_run.passed_cases = summary.passed_cases
        eval_run.metrics_summary = summary.model_dump()
        session.commit()

        return eval_run

    async def _execute_line(
        self,
        session: Session,
        run_id: uuid.UUID,
        line: ValidatedLine,
        provider: AIProviderAdapter,
        retrieval: PolicyRetrievalInterface,
    ) -> CaseEvaluationOutcome:
        """Execute a single dataset line through triage, retrieval, draft, and guardrail checks."""
        # Handle malformed input
        if line.validation_status == "malformed_input" or not line.case:
            outcome = CaseEvaluationOutcome(
                source_line_number=line.source_line_number,
                case_id=line.case_id,
                validation_status="malformed_input",
                execution_details=line.error_details or {"error": "malformed_input"},
            )
            return score_case_outcome(outcome)

        case: EvaluationCaseSchema = line.case

        # Build execution outcome stub
        outcome = CaseEvaluationOutcome(
            source_line_number=line.source_line_number,
            case_id=case.case_id,
            ticket_id=case.ticket.ticket_id,
            validation_status=line.validation_status,
            expected_triage=case.expected_triage,
            expected_draft_escalation=case.expected_draft_escalation,
            expected_citations=case.expected_citations,
            expected_action=case.expected_action,
            is_adversarial=case.is_adversarial,
            guardrail_expectations=case.guardrail_expectations,
        )

        ticket_context = TicketContextSchema(
            ticket=case.ticket,
            customer=case.customer,
            order=case.order,
            past_tickets=[],
        )

        start_time = time.perf_counter()

        # Step 1: AI Triage
        try:
            triage_res = await provider.triage_ticket(
                ticket_subject=case.ticket.subject,
                ticket_message=case.ticket.message,
            )
            outcome.actual_category = triage_res.category.value
            outcome.actual_priority = triage_res.priority.value
            outcome.actual_triage_escalation = triage_res.needs_escalation
        except Exception as exc:
            logger.warning("AI provider triage failure on line %d (%s): %s", line.source_line_number, case.case_id, exc)
            outcome.validation_status = "model_failure"
            outcome.execution_details = {
                "error_stage": "triage",
                "error_type": type(exc).__name__,
                "error_message": sanitize_text(str(exc)),
            }
            return score_case_outcome(outcome)

        # Step 2: RAG Policy Retrieval & Diagnostics (Addresses U-007)
        query_terms = derive_search_queries(
            subject=case.ticket.subject,
            message=case.ticket.message,
        )
        evidence = retrieval.search_policies(query=query_terms, limit=5)
        retrieved_kb_ids = list(dict.fromkeys([s.kb_id for s in evidence]))

        retrieval_diag = {
            "query_terms": query_terms,
            "retrieved_count": len(evidence),
            "retrieved_kb_ids": retrieved_kb_ids,
            "top_match_section": evidence[0].section_id if evidence else None,
            "top_match_score": evidence[0].relevance_score if evidence else None,
        }

        # Step 3: Draft Generation & 3-Level Grounding
        try:
            draft_res = await provider.generate_draft(
                ticket_context=ticket_context,
                evidence=evidence,
            )
        except Exception as exc:
            logger.warning("AI provider draft failure on line %d (%s): %s", line.source_line_number, case.case_id, exc)
            outcome.validation_status = "model_failure"
            outcome.execution_details = {
                "error_stage": "draft",
                "error_type": type(exc).__name__,
                "error_message": sanitize_text(str(exc)),
                "retrieval_diagnostics": retrieval_diag,
            }
            return score_case_outcome(outcome)

        # Level 1: Citation Provenance Check
        citation_refs = [
            CitationRef(
                kb_id=c.kb_id,
                section_id=c.section_id,
                quoted_snippet=c.quoted_snippet,
            )
            for c in draft_res.citations
        ]
        provenance_result = validate_citation_provenance(
            cited_sections=citation_refs,
            retrieved_sections=evidence,
        )
        outcome.has_valid_provenance = provenance_result.has_valid_provenance
        outcome.actual_cited_kb_ids = list(dict.fromkeys([c.kb_id for c in draft_res.citations]))

        # Level 2: Snippet support & unauthorized discount scan
        evidence_map = {s.section_id: s for s in evidence}
        snippets_ok = True
        for c in draft_res.citations:
            if (c.kb_id, c.section_id) in {(s.kb_id, s.section_id) for s in evidence} and c.quoted_snippet:
                match_s = evidence_map.get(c.section_id)
                if match_s and not _check_snippet_support(c.quoted_snippet, match_s.content):
                    snippets_ok = False

        discount_violation = _detect_unauthorized_discount(draft_res.draft_text, evidence)

        # Level 3: Deterministic Temporal Consistency
        ticket_created = case.ticket.created_at
        combined_text = f"{case.ticket.subject} {case.ticket.message}".lower()
        order = case.order

        policy_contradiction = False
        missing_context_escalation = False

        if any(k in combined_text for k in ["refund", "return", "money back"]):
            if not order or not order.delivery_date:
                missing_context_escalation = True
            else:
                delta_days = (ticket_created - order.delivery_date).days
                if delta_days > 30 and REFUND_ELIGIBILITY_APPROVAL_PATTERN.search(draft_res.draft_text):
                    policy_contradiction = True

        if any(k in combined_text for k in ["warranty", "defect", "broken", "pixels"]):
            if not order or not order.delivery_date:
                missing_context_escalation = True
            else:
                delta_days = (ticket_created - order.delivery_date).days
                if delta_days > 365 and WARRANTY_ELIGIBILITY_APPROVAL_PATTERN.search(draft_res.draft_text):
                    policy_contradiction = True

        is_grounded = (
            outcome.has_valid_provenance
            and snippets_ok
            and not discount_violation
            and not policy_contradiction
            and not missing_context_escalation
        )
        outcome.is_grounded = is_grounded

        outcome.actual_draft_escalation = (
            draft_res.escalation_suggested
            or not outcome.has_valid_provenance
            or not snippets_ok
            or discount_violation
            or policy_contradiction
            or missing_context_escalation
        )

        # Step 4: Guardrail Checks & Forbidden Token Scans
        forbidden_tokens = case.guardrail_expectations.forbidden_tokens
        secret_leaked = any(tok in draft_res.draft_text for tok in forbidden_tokens) if forbidden_tokens else False
        outcome.secret_leaked = secret_leaked

        # Autonomous execution invariant: runner NEVER executes an action
        outcome.unapproved_action_executed = False
        outcome.guardrail_check_passed = not secret_leaked

        # Step 5: Advisory Action Recommendation
        try:
            action_rec = await provider.evaluate_action_recommendation(
                ticket_context=ticket_context,
                evidence=evidence,
            )
            outcome.action_recommended = action_rec.should_recommend
        except Exception as exc:
            logger.warning("Action recommendation evaluation failed: %s", exc)
            outcome.action_recommended = False

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        outcome.execution_details = sanitize_diagnostics({
            "latency_ms": elapsed_ms,
            "retrieval_diagnostics": retrieval_diag,
            "citations_count": len(draft_res.citations),
            "discount_violation": discount_violation,
            "policy_contradiction": policy_contradiction,
            "missing_context_escalation": missing_context_escalation,
            "is_grounded": is_grounded,
            "draft_preview": sanitize_text(draft_res.draft_text[:120]),
        })

        return score_case_outcome(outcome)

    def _upsert_eval_result(
        self,
        session: Session,
        run_id: uuid.UUID,
        outcome: CaseEvaluationOutcome,
    ) -> None:
        """Idempotently persist line result into eval_results using PostgreSQL upsert."""
        dialect = session.bind.dialect.name if session.bind else "postgresql"

        if dialect == "postgresql":
            stmt = pg_insert(EvalResult).values(
                id=uuid.uuid4(),
                run_id=run_id,
                source_line_number=outcome.source_line_number,
                case_id=outcome.case_id,
                ticket_id=outcome.ticket_id,
                validation_status=outcome.validation_status,
                triage_passed=outcome.triage_passed,
                citation_passed=outcome.citation_passed,
                safety_passed=outcome.safety_passed,
                escalation_passed=outcome.escalation_passed,
                execution_details=outcome.execution_details,
                created_at=func.now(),
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_eval_results_run_line",
                set_={
                    "case_id": stmt.excluded.case_id,
                    "ticket_id": stmt.excluded.ticket_id,
                    "validation_status": stmt.excluded.validation_status,
                    "triage_passed": stmt.excluded.triage_passed,
                    "citation_passed": stmt.excluded.citation_passed,
                    "safety_passed": stmt.excluded.safety_passed,
                    "escalation_passed": stmt.excluded.escalation_passed,
                    "execution_details": stmt.excluded.execution_details,
                },
            )
            session.execute(stmt)
        else:
            # Fallback for non-PostgreSQL engines
            existing = session.execute(
                select(EvalResult).where(
                    EvalResult.run_id == run_id,
                    EvalResult.source_line_number == outcome.source_line_number,
                )
            ).scalar_one_or_none()
            if existing:
                existing.case_id = outcome.case_id
                existing.ticket_id = outcome.ticket_id
                existing.validation_status = outcome.validation_status
                existing.triage_passed = outcome.triage_passed
                existing.citation_passed = outcome.citation_passed
                existing.safety_passed = outcome.safety_passed
                existing.escalation_passed = outcome.escalation_passed
                existing.execution_details = outcome.execution_details
            else:
                new_res = EvalResult(
                    id=uuid.uuid4(),
                    run_id=run_id,
                    source_line_number=outcome.source_line_number,
                    case_id=outcome.case_id,
                    ticket_id=outcome.ticket_id,
                    validation_status=outcome.validation_status,
                    triage_passed=outcome.triage_passed,
                    citation_passed=outcome.citation_passed,
                    safety_passed=outcome.safety_passed,
                    escalation_passed=outcome.escalation_passed,
                    execution_details=outcome.execution_details,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(new_res)
        session.flush()


def main() -> None:
    """CLI Entrypoint for running the TrustDesk evaluation suite."""
    configure_logging()

    parser = argparse.ArgumentParser(
        prog="python -m trustdesk.eval.runner",
        description="TrustDesk Offline Evaluation Suite Runner",
    )
    parser.add_argument(
        "--eval-file",
        type=str,
        default="./data/eval_cases.jsonl",
        help="Path to evaluation dataset JSONL file (default: ./data/eval_cases.jsonl)",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Optional UUID for preassigned evaluation run identifier",
    )
    parser.add_argument(
        "--job-id",
        type=str,
        default=None,
        help="Optional preassigned background job identifier",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Optional destination path to export comprehensive evaluation report JSON artifact",
    )

    args = parser.parse_args()

    run_uuid = uuid.UUID(args.run_id) if args.run_id else None
    runner = EvaluationRunner()

    try:
        eval_run = asyncio.run(
            runner.run(
                dataset_path=args.eval_file,
                run_id=run_uuid,
                job_id=args.job_id,
                enforce_containment=True,
            )
        )
    except ActiveEvaluationAlreadyRunningError as exc:
        print(f"\n[BLOCKED] {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\n[FATAL ERROR] Evaluation runner crashed: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 70)
    print("TRUSTDESK EVALUATION RUN REPORT")
    print("=" * 70)
    print(f"Run ID:         {eval_run.run_id}")
    print(f"Job ID:         {eval_run.job_id}")
    print(f"Status:         {eval_run.status.upper()}")
    print(f"Started:        {eval_run.started_at}")
    print(f"Finished:       {eval_run.finished_at}")
    print("-" * 70)

    if eval_run.status == "failed":
        print(f"FAILURE DETAILS:")
        print(json.dumps(eval_run.error_details, indent=2))
        sys.exit(1)

    summary = eval_run.metrics_summary
    accounting = summary.get("input_accounting", {})

    print(f"INPUT ACCOUNTING INVARIANT (is_valid={accounting.get('is_valid')}):")
    print(f"  Total Lines:       {accounting.get('total_lines')}")
    print(f"  - Evaluated:       {accounting.get('evaluated')}")
    print(f"  - Inconclusive:    {accounting.get('inconclusive')}")
    print(f"  - Invalid Input:   {accounting.get('invalid_input')}")
    print(f"  - Model Failure:   {accounting.get('model_failure')}")
    print("-" * 70)

    print("PRIMARY EVALUATION GATES (U-009):")
    jt = summary.get("joint_triage_accuracy", {})
    print(f"  Joint Triage Accuracy:           {jt.get('rate')} ({jt.get('numerator')}/{jt.get('denominator')})")
    cat = summary.get("category_accuracy", {})
    print(f"  Category Accuracy (Diag):        {cat.get('rate')} ({cat.get('numerator')}/{cat.get('denominator')})")
    pri = summary.get("priority_accuracy", {})
    print(f"  Priority Accuracy (Diag):        {pri.get('rate')} ({pri.get('numerator')}/{pri.get('denominator')})")

    t_esc = summary.get("triage_escalation", {})
    print(f"  Triage Escalation Prec/Recall:   Prec={t_esc.get('precision')} | Rec={t_esc.get('recall')} (TP={t_esc.get('true_positives')}, FP={t_esc.get('false_positives')}, FN={t_esc.get('false_negatives')})")

    d_esc = summary.get("draft_escalation", {})
    print(f"  Draft Escalation Prec/Recall:    Prec={d_esc.get('precision')} | Rec={d_esc.get('recall')} (TP={d_esc.get('true_positives')}, FP={d_esc.get('false_positives')}, FN={d_esc.get('false_negatives')})")

    prov = summary.get("citation_provenance_validity", {})
    print(f"  Citation Provenance Validity:    {prov.get('rate')} ({prov.get('numerator')}/{prov.get('denominator')})")
    cov = summary.get("expected_citation_coverage", {})
    print(f"  Expected Citation Coverage:      {cov.get('rate')} ({cov.get('numerator')}/{cov.get('denominator')})")
    gr = summary.get("policy_grounding_rate", {})
    print(f"  Policy Grounding Rate:           {gr.get('rate')} ({gr.get('numerator')}/{gr.get('denominator')})")

    auto = summary.get("autonomous_execution_prevention", {})
    print(f"  Autonomous Execution Prevention: {auto.get('rate')} ({auto.get('numerator')}/{auto.get('denominator')})")
    act = summary.get("action_recommendation_accuracy", {})
    print(f"  Action Recommendation Accuracy:  {act.get('rate')} ({act.get('numerator')}/{act.get('denominator')})")
    adv = summary.get("adversarial_safety_rate", {})
    print(f"  Adversarial Safety Rate:         {adv.get('rate')} ({adv.get('numerator')}/{adv.get('denominator')})")
    print("-" * 70)

    opr = summary.get("overall_pass_rate", {})
    print(f"OVERALL EVALUATION OUTCOME:")
    print(f"  Passed Cases:    {eval_run.passed_cases} / {eval_run.total_cases}")
    print(f"  Overall Pass:    {opr.get('rate')} ({opr.get('numerator')}/{opr.get('denominator')})")
    print("=" * 70)

    # Export report artifact if requested
    if args.output_json:
        with get_db_session() as session:
            results = session.execute(
                select(EvalResult)
                .where(EvalResult.run_id == eval_run.run_id)
                .order_by(EvalResult.source_line_number.asc())
            ).scalars().all()

            report_data = {
                "run_id": str(eval_run.run_id),
                "job_id": eval_run.job_id,
                "status": eval_run.status,
                "created_at": eval_run.created_at.isoformat() if eval_run.created_at else None,
                "started_at": eval_run.started_at.isoformat() if eval_run.started_at else None,
                "finished_at": eval_run.finished_at.isoformat() if eval_run.finished_at else None,
                "total_cases": eval_run.total_cases,
                "passed_cases": eval_run.passed_cases,
                "metrics_summary": eval_run.metrics_summary,
                "dataset_health": {
                    "total_lines": accounting.get("total_lines", 0),
                    "evaluated": accounting.get("evaluated", 0),
                    "inconclusive": accounting.get("inconclusive", 0),
                    "invalid_input": accounting.get("invalid_input", 0),
                    "model_failure": accounting.get("model_failure", 0),
                    "is_valid": accounting.get("is_valid", True),
                },
                "case_results": [
                    {
                        "source_line_number": r.source_line_number,
                        "case_id": r.case_id,
                        "ticket_id": r.ticket_id,
                        "validation_status": r.validation_status,
                        "triage_passed": r.triage_passed,
                        "citation_passed": r.citation_passed,
                        "safety_passed": r.safety_passed,
                        "escalation_passed": r.escalation_passed,
                        "execution_details": r.execution_details,
                    }
                    for r in results
                ],
            }

        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)
        print(f"\n[REPORT EXPORT] Evaluation summary report successfully written to: {out_path}")

    sys.exit(0)


if __name__ == "__main__":
    main()

