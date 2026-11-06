from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trustdesk.eval.loader import (
    DatasetEmptyError,
    DatasetNotFoundError,
    DatasetPathSecurityError,
    DatasetUnreadableError,
    DuplicateCaseIDError,
    load_and_validate_dataset,
)
from trustdesk.schemas.eval import (
    EvaluationCaseSchema,
    get_approved_data_dir,
    validate_canonical_dataset_path,
)
from trustdesk.schemas.triage import TicketCategory, TicketPriority

DATASET_PATH = Path("data/eval_cases.jsonl")
KB_DOCUMENTS_PATH = Path("data/kb_documents.json")


def test_valid_jsonl_parsing_and_input_accounting() -> None:
    """Verifies that data/eval_cases.jsonl parses cleanly and satisfies input accounting."""
    result = load_and_validate_dataset(DATASET_PATH)

    assert result.is_valid is True
    assert result.fatal_error is None
    assert result.total_lines == 18
    assert result.valid_cases_count == 17
    assert result.inconclusive_count == 1
    assert result.malformed_count == 0

    # Strict input accounting invariant
    assert result.total_lines == (
        result.valid_cases_count + result.inconclusive_count + result.malformed_count
    )


def test_all_18_fixture_schemas_valid() -> None:
    """Verifies that each of the 18 fixture lines conforms to EvaluationCaseSchema."""
    result = load_and_validate_dataset(DATASET_PATH)
    assert len(result.lines) == 18

    for line in result.lines:
        assert line.case is not None
        assert isinstance(line.case, EvaluationCaseSchema)
        assert line.case.ticket.ticket_id.startswith("TIK-EVAL-")
        assert line.case.customer.customer_id.startswith("CUST-EVAL-")


def test_unique_case_ids() -> None:
    """Verifies that all 18 case IDs are unique and match EVAL-001 through EVAL-018."""
    result = load_and_validate_dataset(DATASET_PATH)
    case_ids = [line.case.case_id for line in result.lines if line.case]

    assert len(case_ids) == 18
    assert len(set(case_ids)) == 18

    expected_ids = {f"EVAL-{i:03d}" for i in range(1, 19)}
    assert set(case_ids) == expected_ids


def test_stable_source_line_numbering() -> None:
    """Verifies that source_line_number is 1-indexed and monotonically increasing."""
    result = load_and_validate_dataset(DATASET_PATH)

    for expected_line_num, line in enumerate(result.lines, start=1):
        assert line.source_line_number == expected_line_num


def test_duplicate_case_id_rejection(tmp_path: Path) -> None:
    """Verifies pre-flight fatal rejection when duplicate valid case IDs exist."""
    dup_file = tmp_path / "dup_cases.jsonl"
    result = load_and_validate_dataset(DATASET_PATH)
    first_line_json = result.lines[0].case.model_dump_json()

    # Write two identical lines with case_id EVAL-001
    dup_file.write_text(f"{first_line_json}\n{first_line_json}\n", encoding="utf-8")

    # Fatal error raised when raise_on_fatal=True
    with pytest.raises(DuplicateCaseIDError) as exc_info:
        load_and_validate_dataset(dup_file, raise_on_fatal=True)
    assert "Duplicate valid case_id 'EVAL-001' detected" in str(exc_info.value)

    # Populates fatal_error when raise_on_fatal=False
    non_fatal_result = load_and_validate_dataset(dup_file, raise_on_fatal=False)
    assert non_fatal_result.is_valid is False
    assert non_fatal_result.fatal_error is not None
    assert "Duplicate valid case_id 'EVAL-001'" in non_fatal_result.fatal_error


def test_missing_dataset() -> None:
    """Verifies error handling when dataset file does not exist on disk."""
    missing_path = Path("data/non_existent_file.jsonl")

    with pytest.raises(DatasetNotFoundError):
        load_and_validate_dataset(missing_path, raise_on_fatal=True)

    non_fatal = load_and_validate_dataset(missing_path, raise_on_fatal=False)
    assert non_fatal.is_valid is False
    assert non_fatal.total_lines == 0
    assert "not found" in non_fatal.fatal_error.lower()


def test_empty_dataset(tmp_path: Path) -> None:
    """Verifies fatal error handling when dataset file has 0 lines."""
    empty_file = tmp_path / "empty_dataset.jsonl"
    empty_file.write_text("", encoding="utf-8")

    with pytest.raises(DatasetEmptyError):
        load_and_validate_dataset(empty_file, raise_on_fatal=True)

    non_fatal = load_and_validate_dataset(empty_file, raise_on_fatal=False)
    assert non_fatal.is_valid is False
    assert non_fatal.total_lines == 0
    assert "empty (0 lines)" in non_fatal.fatal_error


def test_malformed_json_lines(tmp_path: Path) -> None:
    """Verifies that malformed JSON syntax is flagged as malformed_input without aborting subsequent lines."""
    bad_file = tmp_path / "malformed.jsonl"
    result = load_and_validate_dataset(DATASET_PATH)
    valid_line_json = result.lines[0].case.model_dump_json()

    bad_content = f"{{not valid json\n{valid_line_json}\n"
    bad_file.write_text(bad_content, encoding="utf-8")

    res = load_and_validate_dataset(bad_file, raise_on_fatal=False)
    assert res.total_lines == 2
    assert res.malformed_count == 1
    assert res.valid_cases_count == 1
    assert res.is_valid is False

    assert res.lines[0].source_line_number == 1
    assert res.lines[0].validation_status == "malformed_input"
    assert res.lines[0].error_details["error"] == "JSONDecodeError"

    assert res.lines[1].source_line_number == 2
    assert res.lines[1].validation_status == "valid"


def test_schema_invalid_records(tmp_path: Path) -> None:
    """Verifies that schema validation failures are captured under malformed_input with diagnostics."""
    schema_bad_file = tmp_path / "bad_schema.jsonl"
    raw_bad_record = {
        "case_id": "EVAL-BAD-01",
        "description": "Missing required ticket fixture",
        "scenario_type": "invalid",
        # 'ticket' is omitted
        "customer": {"customer_id": "CUST-001", "created_at": "2026-01-01T00:00:00Z"},
    }
    schema_bad_file.write_text(json.dumps(raw_bad_record) + "\n", encoding="utf-8")

    res = load_and_validate_dataset(schema_bad_file, raise_on_fatal=False)
    assert res.total_lines == 1
    assert res.malformed_count == 1
    assert res.valid_cases_count == 0
    assert res.lines[0].validation_status == "malformed_input"
    assert res.lines[0].case_id == "EVAL-BAD-01"
    assert res.lines[0].error_details["error"] == "ValidationError"


def test_missing_ground_truth_inconclusive() -> None:
    """Verifies that EVAL-017 is assigned inconclusive status without counting as malformed."""
    result = load_and_validate_dataset(DATASET_PATH)
    eval_017 = next(line for line in result.lines if line.case_id == "EVAL-017")

    assert eval_017.validation_status == "inconclusive"
    assert eval_017.case is not None
    assert eval_017.case.expected_triage is None
    assert eval_017.case.expected_draft_escalation is None
    assert eval_017.error_details is None


def test_frozen_timestamp_validation() -> None:
    """Verifies that all 18 cases use consistent frozen UTC timestamps."""
    result = load_and_validate_dataset(DATASET_PATH)

    for line in result.lines:
        ticket = line.case.ticket
        assert ticket.created_at.tzinfo is not None
        assert ticket.created_at == datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)

        customer = line.case.customer
        assert customer.created_at.tzinfo is not None
        assert customer.created_at <= ticket.created_at

        if line.case.order:
            order = line.case.order
            assert order.order_date.tzinfo is not None
            assert order.order_date <= ticket.created_at
            if order.delivery_date:
                assert order.delivery_date.tzinfo is not None
                assert order.delivery_date >= order.order_date


def test_refund_and_warranty_date_calculations() -> None:
    """Verifies that temporal window calculations match authoritative policies."""
    result = load_and_validate_dataset(DATASET_PATH)
    cases = {line.case_id: line.case for line in result.lines}

    # EVAL-001: 12 days delivery to ticket <= 30 days -> eligible refund
    eval_001 = cases["EVAL-001"]
    delta_001 = (eval_001.ticket.created_at - eval_001.order.delivery_date).days
    assert delta_001 == 12
    assert delta_001 <= 30
    assert eval_001.expected_action.should_recommend is True
    assert eval_001.expected_draft_escalation is False

    # EVAL-002: 45 days delivery to ticket > 30 days -> expired refund
    eval_002 = cases["EVAL-002"]
    delta_002 = (eval_002.ticket.created_at - eval_002.order.delivery_date).days
    assert delta_002 == 45
    assert delta_002 > 30
    assert eval_002.expected_action.should_recommend is False
    assert eval_002.expected_draft_escalation is False

    # EVAL-003: 184 days delivery to ticket <= 365 days -> valid warranty
    eval_003 = cases["EVAL-003"]
    delta_003 = (eval_003.ticket.created_at - eval_003.order.delivery_date).days
    assert delta_003 == 184
    assert delta_003 <= 365
    assert eval_003.expected_draft_escalation is False

    # EVAL-004: 400 days delivery to ticket > 365 days -> expired warranty
    eval_004 = cases["EVAL-004"]
    delta_004 = (eval_004.ticket.created_at - eval_004.order.delivery_date).days
    assert delta_004 == 400
    assert delta_004 > 365
    assert eval_004.expected_draft_escalation is False

    # EVAL-018: delivery_date is None -> missing delivery date, draft escalation required
    eval_018 = cases["EVAL-018"]
    assert eval_018.order is not None
    assert eval_018.order.delivery_date is None
    assert eval_018.expected_draft_escalation is True


def test_citation_document_id_existence() -> None:
    """Verifies that all expected_citations reference actual documents in data/kb_documents.json."""
    kb_data = json.loads(KB_DOCUMENTS_PATH.read_text(encoding="utf-8"))
    valid_kb_ids = {doc["kb_id"] for doc in kb_data}

    result = load_and_validate_dataset(DATASET_PATH)

    for line in result.lines:
        for citation in line.case.expected_citations:
            assert citation in valid_kb_ids, (
                f"Case {line.case_id} references unknown KB document '{citation}'"
            )


def test_eval_016_expected_labels() -> None:
    """Verifies that EVAL-016 has complete ground truth labels despite simulated timeout."""
    result = load_and_validate_dataset(DATASET_PATH)
    eval_016 = next(line for line in result.lines if line.case_id == "EVAL-016")

    assert eval_016.validation_status == "valid"
    assert eval_016.case.expected_triage is not None
    assert eval_016.case.expected_triage.category == TicketCategory.REFUND
    assert eval_016.case.expected_triage.priority == TicketPriority.HIGH
    assert eval_016.case.expected_triage.needs_escalation is False
    assert eval_016.case.expected_draft_escalation is False

    combined_text = f"{eval_016.case.ticket.subject} {eval_016.case.ticket.message}".lower()
    assert "simulate_timeout" in combined_text


def test_synthetic_adversarial_fixture_safety() -> None:
    """Verifies that adversarial fixtures (EVAL-014, EVAL-015) specify guardrail invariants."""
    result = load_and_validate_dataset(DATASET_PATH)
    cases = {line.case_id: line.case for line in result.lines}

    # EVAL-014: Prompt injection
    eval_014 = cases["EVAL-014"]
    assert eval_014.is_adversarial is True
    assert eval_014.adversarial_type == "prompt_injection"
    assert eval_014.guardrail_expectations.forbid_unapproved_action is True
    assert eval_014.guardrail_expectations.forbid_secret_leak is True
    assert "issue_direct_refund" in eval_014.guardrail_expectations.forbidden_tokens

    # EVAL-015: Poisoned KB document
    eval_015 = cases["EVAL-015"]
    assert eval_015.is_adversarial is True
    assert eval_015.adversarial_type == "knowledge_poisoning"
    assert eval_015.guardrail_expectations.forbid_unapproved_action is True
    assert eval_015.guardrail_expectations.forbid_secret_leak is True
    assert "SECRET-KEY-ALPHA-9999" in eval_015.guardrail_expectations.forbidden_tokens


# ---------------------------------------------------------------------------
# Canonical Dataset Path & Symlink Escape Security Tests
# ---------------------------------------------------------------------------

def test_canonical_path_valid_paths() -> None:
    """Verifies that legitimate relative and absolute dataset paths within approved data/ resolve cleanly."""
    approved_dir = get_approved_data_dir()
    expected_file = approved_dir / "eval_cases.jsonl"

    for valid_input in [
        "./data/eval_cases.jsonl",
        "data/eval_cases.jsonl",
        str(expected_file),
        expected_file,
    ]:
        resolved = validate_canonical_dataset_path(valid_input)
        assert resolved == expected_file
        assert resolved.is_file()


def test_canonical_path_traversal_rejection() -> None:
    """Verifies that path traversal sequences (..) and null bytes are rejected."""
    bad_inputs = [
        "../../etc/passwd",
        "data/../../etc/passwd.jsonl",
        "data/eval_cases.jsonl\x00.jsonl",
        "../data/eval_cases.jsonl",
        "",
        "   ",
    ]
    for bad in bad_inputs:
        with pytest.raises(ValueError) as exc_info:
            validate_canonical_dataset_path(bad)
        err = str(exc_info.value).lower()
        assert "traversal" in err or "extension" in err or "empty" in err or "outside" in err


def test_canonical_path_absolute_escape_rejection() -> None:
    """Verifies that absolute paths outside the approved data directory are rejected."""
    outside_paths = [
        "/etc/passwd.jsonl",
        "/tmp/outside_eval.jsonl",
        "/var/log/system.jsonl",
    ]
    for outside in outside_paths:
        with pytest.raises(ValueError) as exc_info:
            validate_canonical_dataset_path(outside)
        assert "outside the approved data directory" in str(exc_info.value)


def test_canonical_path_symlink_escape_rejection(tmp_path: Path) -> None:
    """Verifies that symlinks resolving outside the approved directory are strictly rejected."""
    import os

    outside_target = tmp_path / "target.jsonl"
    outside_target.write_text("{}", encoding="utf-8")

    approved_test_dir = tmp_path / "mock_data"
    approved_test_dir.mkdir()

    symlink_file = approved_test_dir / "escape_link.jsonl"
    os.symlink(outside_target.resolve(), symlink_file)

    # 1. Direct canonical validator rejects symlink pointing outside
    with pytest.raises(ValueError) as exc_info:
        validate_canonical_dataset_path(symlink_file, approved_data_dir=approved_test_dir)
    assert "outside the approved data directory" in str(exc_info.value)

    # 2. Loader with enforce_containment=True raises DatasetPathSecurityError
    with pytest.raises(DatasetPathSecurityError):
        load_and_validate_dataset(
            symlink_file,
            raise_on_fatal=True,
            enforce_containment=True,
            allowed_dir=approved_test_dir,
        )

    # 3. Non-fatal loader populates fatal_error without crashing
    non_fatal = load_and_validate_dataset(
        symlink_file,
        raise_on_fatal=False,
        enforce_containment=True,
        allowed_dir=approved_test_dir,
    )
    assert non_fatal.is_valid is False
    assert "containment violation" in non_fatal.fatal_error


def test_canonical_path_missing_file_handling() -> None:
    """Verifies that non-existent paths within data/ pass containment but fail existence check."""
    missing_in_data = "data/non_existent_file_12345.jsonl"

    # Canonical containment passes because the path resolves inside approved data/
    resolved = validate_canonical_dataset_path(missing_in_data)
    assert resolved.name == "non_existent_file_12345.jsonl"
    assert resolved.parent == get_approved_data_dir()

    # Loader fails with DatasetNotFoundError
    with pytest.raises(DatasetNotFoundError):
        load_and_validate_dataset(missing_in_data, raise_on_fatal=True, enforce_containment=True)


