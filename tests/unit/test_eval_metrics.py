from __future__ import annotations

import json

import pytest

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
from trustdesk.schemas.eval import (
    CaseEvaluationOutcome,
    ExpectedActionSchema,
    ExpectedTriageSchema,
    GuardrailExpectationsSchema,
    InputAccounting,
    MetricsSummary,
)
from trustdesk.schemas.triage import TicketCategory, TicketPriority


def _make_valid_outcome(
    source_line_number: int = 1,
    case_id: str = "EVAL-001",
    cat: TicketCategory = TicketCategory.REFUND,
    pri: TicketPriority = TicketPriority.HIGH,
    triage_esc: bool = False,
    draft_esc: bool = False,
    expected_citations: list[str] | None = None,
    actual_citations: list[str] | None = None,
    prov_valid: bool = True,
    grounded: bool = True,
    should_recommend_action: bool = True,
    action_recommended: bool = True,
    is_adversarial: bool = False,
) -> CaseEvaluationOutcome:
    """Helper to construct a fully populated, passing CaseEvaluationOutcome."""
    return CaseEvaluationOutcome(
        source_line_number=source_line_number,
        case_id=case_id,
        ticket_id=f"TIK-{case_id}",
        validation_status="valid",
        expected_triage=ExpectedTriageSchema(
            category=cat,
            priority=pri,
            needs_escalation=triage_esc,
        ),
        expected_draft_escalation=draft_esc,
        expected_citations=expected_citations if expected_citations is not None else ["KB-REFUND-001"],
        expected_action=ExpectedActionSchema(
            action_type="start_refund_review",
            should_recommend=should_recommend_action,
        ),
        is_adversarial=is_adversarial,
        guardrail_expectations=GuardrailExpectationsSchema(
            expected_guardrail_outcome="passed",
            forbid_unapproved_action=True,
            forbid_secret_leak=True,
        ),
        actual_category=cat.value,
        actual_priority=pri.value,
        actual_triage_escalation=triage_esc,
        actual_draft_escalation=draft_esc,
        actual_cited_kb_ids=actual_citations if actual_citations is not None else ["KB-REFUND-001"],
        has_valid_provenance=prov_valid,
        is_grounded=grounded,
        action_recommended=action_recommended,
        unapproved_action_executed=False,
        secret_leaked=False,
        guardrail_check_passed=True,
    )


def test_perfect_predictions() -> None:
    """1. Verifies that all metrics report 1.0 (100%) when all predictions match ground truth."""
    outcomes = [
        _make_valid_outcome(1, "EVAL-001", triage_esc=True, draft_esc=True, is_adversarial=True),
        _make_valid_outcome(2, "EVAL-002", triage_esc=False, draft_esc=False, is_adversarial=False),
    ]
    summary = calculate_metrics(outcomes)

    assert summary.joint_triage_accuracy.rate == 1.0
    assert summary.joint_triage_accuracy.numerator == 2
    assert summary.joint_triage_accuracy.denominator == 2

    assert summary.category_accuracy.rate == 1.0
    assert summary.priority_accuracy.rate == 1.0

    assert summary.triage_escalation.precision == 1.0
    assert summary.triage_escalation.recall == 1.0

    assert summary.draft_escalation.precision == 1.0
    assert summary.draft_escalation.recall == 1.0

    assert summary.citation_provenance_validity.rate == 1.0
    assert summary.expected_citation_coverage.rate == 1.0
    assert summary.policy_grounding_rate.rate == 1.0

    assert summary.autonomous_execution_prevention.rate == 1.0
    assert summary.action_recommendation_accuracy.rate == 1.0
    assert summary.adversarial_safety_rate.rate == 1.0

    assert summary.passed_cases == 2
    assert summary.overall_pass_rate.rate == 1.0


def test_incorrect_category() -> None:
    """2. Verifies that an incorrect category lowers category and joint accuracy while priority holds."""
    outcome = _make_valid_outcome(1, "EVAL-001", cat=TicketCategory.REFUND)
    outcome.actual_category = TicketCategory.WARRANTY.value  # Incorrect category

    joint, cat, pri = calculate_triage_accuracy([outcome])
    assert cat.rate == 0.0
    assert cat.numerator == 0
    assert cat.denominator == 1

    assert pri.rate == 1.0
    assert pri.numerator == 1

    assert joint.rate == 0.0
    assert joint.numerator == 0


def test_incorrect_priority() -> None:
    """3. Verifies that an incorrect priority lowers priority and joint accuracy while category holds."""
    outcome = _make_valid_outcome(1, "EVAL-001", pri=TicketPriority.HIGH)
    outcome.actual_priority = TicketPriority.LOW.value  # Incorrect priority

    joint, cat, pri = calculate_triage_accuracy([outcome])
    assert cat.rate == 1.0
    assert pri.rate == 0.0
    assert joint.rate == 0.0


def test_incorrect_triage_escalation() -> None:
    """4. Verifies that mismatched triage escalation flag lowers joint triage accuracy."""
    outcome = _make_valid_outcome(1, "EVAL-001", triage_esc=False)
    outcome.actual_triage_escalation = True  # Model false positive on escalation

    joint, cat, pri = calculate_triage_accuracy([outcome])
    # Category and priority matched
    assert cat.rate == 1.0
    assert pri.rate == 1.0
    # Joint accuracy fails because triage escalation flag did not match
    assert joint.rate == 0.0
    assert joint.numerator == 0


def test_incorrect_draft_escalation() -> None:
    """5. Verifies that incorrect draft escalation affects draft precision/recall and fails case pass."""
    outcome = _make_valid_outcome(1, "EVAL-001", draft_esc=False)
    outcome.actual_draft_escalation = True  # FP

    summary = calculate_metrics([outcome])
    assert summary.draft_escalation.false_positives == 1
    assert summary.draft_escalation.precision == 0.0
    assert summary.draft_escalation.recall is None  # Zero expected positives (TP+FN == 0)

    # Triage and citations passed, but draft escalation failed
    scored = score_case_outcome(outcome)
    assert scored.triage_passed is True
    assert scored.escalation_passed is False
    assert scored.case_passed is False


def test_false_positives_and_false_negatives_for_escalation_metrics() -> None:
    """6. Verifies exact precision/recall math for TP, FP, FN, and TN across separated escalation signals."""
    # Create 4 cases for triage escalation:
    # 1. TP: exp=True, act=True
    # 2. FP: exp=False, act=True
    # 3. FN: exp=True, act=False
    # 4. TN: exp=False, act=False
    triage_outcomes = [
        _make_valid_outcome(1, "C1", triage_esc=True),
        _make_valid_outcome(2, "C2", triage_esc=False),
        _make_valid_outcome(3, "C3", triage_esc=True),
        _make_valid_outcome(4, "C4", triage_esc=False),
    ]
    triage_outcomes[0].actual_triage_escalation = True   # TP
    triage_outcomes[1].actual_triage_escalation = True   # FP
    triage_outcomes[2].actual_triage_escalation = False  # FN
    triage_outcomes[3].actual_triage_escalation = False  # TN

    pr = calculate_triage_escalation(triage_outcomes)
    assert pr.true_positives == 1
    assert pr.false_positives == 1
    assert pr.false_negatives == 1
    assert pr.true_negatives == 1
    assert pr.precision == 0.5  # 1 / (1 + 1)
    assert pr.recall == 0.5     # 1 / (1 + 1)

    # Independently verify draft escalation with different distribution:
    # 2 TP, 0 FP, 1 FN => Prec=1.0, Recall=2/3 (~0.6667)
    draft_outcomes = [
        _make_valid_outcome(1, "D1", draft_esc=True),
        _make_valid_outcome(2, "D2", draft_esc=True),
        _make_valid_outcome(3, "D3", draft_esc=True),
    ]
    draft_outcomes[0].actual_draft_escalation = True
    draft_outcomes[1].actual_draft_escalation = True
    draft_outcomes[2].actual_draft_escalation = False

    d_pr = calculate_draft_escalation(draft_outcomes)
    assert d_pr.true_positives == 2
    assert d_pr.false_positives == 0
    assert d_pr.false_negatives == 1
    assert d_pr.precision == 1.0
    assert d_pr.recall == round(2 / 3, 4)


def test_citation_provenance_failure() -> None:
    """7. Verifies Level 1 provenance failure lowers provenance score and fails citation verdict."""
    outcome = _make_valid_outcome(1, "EVAL-012")
    outcome.has_valid_provenance = False  # Hallucinated section

    prov, cov, grounding = calculate_citation_metrics([outcome])
    assert prov.rate == 0.0
    assert prov.numerator == 0
    assert prov.denominator == 1

    scored = score_case_outcome(outcome)
    assert scored.citation_passed is False
    assert scored.case_passed is False


def test_unsupported_claims_despite_valid_citation_ids() -> None:
    """8. Verifies Level 2/3 grounding failure lowers policy_grounding_rate even when provenance is valid."""
    outcome = _make_valid_outcome(1, "EVAL-013")
    outcome.has_valid_provenance = True  # Citations exist in evidence
    outcome.is_grounded = False          # Unauthorized discount or hallucinated eligibility

    prov, cov, grounding = calculate_citation_metrics([outcome])
    assert prov.rate == 1.0
    assert grounding.rate == 0.0
    assert grounding.numerator == 0
    assert grounding.denominator == 1


def test_unauthorized_action_or_guardrail_failure() -> None:
    """9. Verifies that unauthorized execution or secret leak fails safety and blocks case pass."""
    outcome = _make_valid_outcome(1, "EVAL-014", is_adversarial=True)
    outcome.unapproved_action_executed = True  # Autonomous action leak

    auto_exec, action_rec, adv_safety = calculate_safety_metrics([outcome])
    assert auto_exec.rate == 0.0
    assert auto_exec.numerator == 0
    assert adv_safety.rate == 0.0

    scored = score_case_outcome(outcome)
    assert scored.safety_passed is False
    assert scored.case_passed is False


def test_provider_timeout_with_valid_ground_truth() -> None:
    """10. Verifies that model_failure (EVAL-016) participates in triage accuracy denominator and scores 0."""
    outcome = _make_valid_outcome(1, "EVAL-016")
    outcome.validation_status = "model_failure"
    outcome.actual_category = None
    outcome.actual_priority = None

    joint, cat, pri = calculate_triage_accuracy([outcome])
    # Case has valid expected_triage, so denominator must be 1, not 0
    assert cat.denominator == 1
    assert cat.numerator == 0
    assert cat.rate == 0.0

    assert pri.denominator == 1
    assert pri.rate == 0.0

    assert joint.denominator == 1
    assert joint.rate == 0.0

    accounting = calculate_input_accounting([outcome])
    assert accounting.model_failure == 1
    assert accounting.evaluated == 0
    assert accounting.is_valid is True


def test_inconclusive_case_exclusion() -> None:
    """11. Verifies that inconclusive cases (EVAL-017) are excluded from accuracy denominators."""
    inconclusive = CaseEvaluationOutcome(
        source_line_number=1,
        case_id="EVAL-017",
        validation_status="inconclusive",
        expected_triage=None,
        expected_draft_escalation=None,
    )
    valid_case = _make_valid_outcome(2, "EVAL-001")

    joint, cat, pri = calculate_triage_accuracy([inconclusive, valid_case])
    # Denominator must exclude EVAL-017: denominator == 1
    assert cat.denominator == 1
    assert cat.numerator == 1
    assert cat.rate == 1.0

    d_pr = calculate_draft_escalation([inconclusive, valid_case])
    assert d_pr.true_negatives == 1
    assert (d_pr.true_positives + d_pr.false_positives + d_pr.false_negatives + d_pr.true_negatives) == 1

    accounting = calculate_input_accounting([inconclusive, valid_case])
    assert accounting.inconclusive == 1
    assert accounting.evaluated == 1
    assert accounting.total_lines == 2


def test_malformed_input_exclusion() -> None:
    """12. Verifies that malformed input lines are excluded from accuracy denominators but preserved in accounting."""
    malformed = CaseEvaluationOutcome(
        source_line_number=1,
        case_id=None,
        validation_status="malformed_input",
    )
    valid_case = _make_valid_outcome(2, "EVAL-001")

    joint, cat, pri = calculate_triage_accuracy([malformed, valid_case])
    assert cat.denominator == 1
    assert cat.rate == 1.0

    accounting = calculate_input_accounting([malformed, valid_case])
    assert accounting.total_lines == 2
    assert accounting.invalid_input == 1
    assert accounting.evaluated == 1
    assert accounting.is_valid is True


def test_zero_denominator_null_handling() -> None:
    """13. Verifies that zero denominators return null (None), not zero or NaN."""
    summary = calculate_metrics([])

    assert summary.joint_triage_accuracy.rate is None
    assert summary.joint_triage_accuracy.denominator == 0

    assert summary.category_accuracy.rate is None
    assert summary.priority_accuracy.rate is None

    assert summary.triage_escalation.precision is None
    assert summary.triage_escalation.recall is None

    assert summary.draft_escalation.precision is None
    assert summary.draft_escalation.recall is None

    assert summary.citation_provenance_validity.rate is None
    assert summary.expected_citation_coverage.rate is None
    assert summary.policy_grounding_rate.rate is None

    assert summary.autonomous_execution_prevention.rate is None
    assert summary.action_recommendation_accuracy.rate is None
    assert summary.adversarial_safety_rate.rate is None

    assert summary.overall_pass_rate.rate is None


def test_mixed_case_aggregate_scoring() -> None:
    """14. Verifies composite multi-case scoring across all metric dimensions."""
    outcomes = [
        # Case 1: Perfect pass
        _make_valid_outcome(1, "EVAL-001"),
        # Case 2: Wrong category
        _make_valid_outcome(2, "EVAL-002", cat=TicketCategory.REFUND),
        # Case 3: Timeout failure
        _make_valid_outcome(3, "EVAL-016"),
        # Case 4: Inconclusive
        CaseEvaluationOutcome(source_line_number=4, case_id="EVAL-017", validation_status="inconclusive"),
        # Case 5: Malformed
        CaseEvaluationOutcome(source_line_number=5, validation_status="malformed_input"),
    ]
    outcomes[1].actual_category = TicketCategory.WARRANTY.value
    outcomes[2].validation_status = "model_failure"

    summary = calculate_metrics(outcomes)

    # Total lines: 5
    assert summary.input_accounting.total_lines == 5
    assert summary.input_accounting.evaluated == 2
    assert summary.input_accounting.model_failure == 1
    assert summary.input_accounting.inconclusive == 1
    assert summary.input_accounting.invalid_input == 1
    assert summary.input_accounting.is_valid is True

    # Triage evaluatable: Case 1, 2, 3 (denom == 3)
    assert summary.category_accuracy.denominator == 3
    # Case 1 matched, Case 2 mismatched, Case 3 failed
    assert summary.category_accuracy.numerator == 1
    assert summary.category_accuracy.rate == round(1 / 3, 4)

    # Overall passed cases: only Case 1 passed all criteria
    assert summary.passed_cases == 1
    assert summary.overall_pass_rate.rate == round(1 / 5, 4)


def test_complete_input_accounting() -> None:
    """15. Verifies that the input accounting invariant is enforced and validates correctly."""
    outcomes = [
        CaseEvaluationOutcome(source_line_number=1, validation_status="valid"),
        CaseEvaluationOutcome(source_line_number=2, validation_status="evaluated"),
        CaseEvaluationOutcome(source_line_number=3, validation_status="inconclusive"),
        CaseEvaluationOutcome(source_line_number=4, validation_status="malformed_input"),
        CaseEvaluationOutcome(source_line_number=5, validation_status="invalid_input"),
        CaseEvaluationOutcome(source_line_number=6, validation_status="model_failure"),
    ]
    accounting = calculate_input_accounting(outcomes)

    assert accounting.total_lines == 6
    assert accounting.evaluated == 2
    assert accounting.inconclusive == 1
    assert accounting.invalid_input == 2
    assert accounting.model_failure == 1
    assert accounting.is_valid is True
    assert accounting.total_lines == (
        accounting.evaluated + accounting.inconclusive + accounting.invalid_input + accounting.model_failure
    )


def test_deterministic_repeatability() -> None:
    """16. Verifies that repeated evaluation calls on identical inputs yield identical outputs."""
    outcomes = [
        _make_valid_outcome(1, "EVAL-001"),
        _make_valid_outcome(2, "EVAL-002", cat=TicketCategory.SHIPPING),
    ]

    first_run = calculate_metrics(outcomes).model_dump()
    for _ in range(5):
        subsequent_run = calculate_metrics(outcomes).model_dump()
        assert subsequent_run == first_run


def test_json_serialization() -> None:
    """17. Verifies that MetricsSummary cleanly serializes to JSON string and JSONB dict."""
    outcomes = [
        _make_valid_outcome(1, "EVAL-001"),
        CaseEvaluationOutcome(source_line_number=2, validation_status="inconclusive"),
    ]
    summary = calculate_metrics(outcomes)

    # 1. Pydantic model_dump produces primitive dict
    data_dict = summary.model_dump()
    assert isinstance(data_dict, dict)
    assert data_dict["input_accounting"]["total_lines"] == 2

    # 2. JSON string serialization
    json_str = summary.model_dump_json()
    assert isinstance(json_str, str)
    parsed = json.loads(json_str)
    assert parsed["input_accounting"]["total_lines"] == 2

    # 3. Verify nulls serialize as literal None / JSON null
    assert data_dict["adversarial_safety_rate"]["rate"] is None
    assert parsed["adversarial_safety_rate"]["rate"] is None

