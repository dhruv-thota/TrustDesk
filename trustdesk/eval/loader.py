from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from trustdesk.schemas.eval import (
    DatasetValidationResult,
    EvaluationCaseSchema,
    ValidatedLine,
    get_approved_data_dir,
    validate_canonical_dataset_path,
)


class DatasetValidationError(Exception):
    """Base exception for dataset-level fatal validation failures."""
    pass


class DatasetPathSecurityError(DatasetValidationError):
    """Raised when the dataset path violates canonical containment or symlink escape checks."""
    pass


class DatasetNotFoundError(DatasetValidationError):
    """Raised when the specified dataset file does not exist on disk."""
    pass


class DatasetEmptyError(DatasetValidationError):
    """Raised when the evaluation dataset file contains zero lines or is empty."""
    pass


class DatasetUnreadableError(DatasetValidationError):
    """Raised when the evaluation dataset file cannot be read due to OS/permission errors."""
    pass


class DuplicateCaseIDError(DatasetValidationError):
    """Raised when duplicate valid case_id values are detected in the dataset."""
    pass


def load_and_validate_dataset(
    file_path: str | Path,
    raise_on_fatal: bool = True,
    enforce_containment: bool = False,
    allowed_dir: Path | None = None,
) -> DatasetValidationResult:
    """Load and validate an evaluation JSONL dataset file.

    Enforces:
    1. Pre-flight fatal abort on missing, empty (0 lines), or unreadable files.
    2. Optional canonical containment validation preventing directory traversal
       and symlink escapes outside the approved data directory.
    3. 1-indexed source_line_number assignment for every input line.
    4. Rejection of duplicate valid case_id values (fatal duplicate abort).
    5. Distinguishing 'malformed_input' (syntax/schema error) from 'inconclusive'
       (valid case with missing ground truth, e.g. EVAL-017).
    6. Zero AI provider or retrieval service invocation during validation.
    7. Strict alignment with EvalResult.validation_status ('valid', 'inconclusive', 'malformed_input').

    Args:
        file_path: Path to the .jsonl file.
        raise_on_fatal: If True, raises specific DatasetValidationError subclasses
                        on missing, empty, unreadable, duplicate case_id, or containment violations.
                        If False, populates fatal_error in DatasetValidationResult.
        enforce_containment: If True, validates canonical containment within allowed_dir
                             (defaulting to approved project data/ directory) and blocks symlink escapes.
        allowed_dir: Optional custom approved root directory for containment validation.

    Returns:
        DatasetValidationResult containing line-by-line validation records and statistics.
    """
    if enforce_containment or allowed_dir is not None:
        try:
            path = validate_canonical_dataset_path(file_path, approved_data_dir=allowed_dir)
        except ValueError as exc:
            msg = f"Dataset path containment violation: {exc}"
            if raise_on_fatal:
                raise DatasetPathSecurityError(msg) from exc
            return DatasetValidationResult(
                total_lines=0,
                is_valid=False,
                fatal_error=msg,
            )
    else:
        path = Path(file_path).resolve()

    if not path.is_file():
        msg = f"Evaluation dataset file not found: {path}"
        if raise_on_fatal:
            raise DatasetNotFoundError(msg)
        return DatasetValidationResult(
            total_lines=0,
            is_valid=False,
            fatal_error=msg,
        )

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:
        msg = f"Failed to read evaluation dataset file '{path}': {exc}"
        if raise_on_fatal:
            raise DatasetUnreadableError(msg) from exc
        return DatasetValidationResult(
            total_lines=0,
            is_valid=False,
            fatal_error=msg,
        )

    # Split lines preserving raw line positions, stripping trailing EOF newlines
    raw_lines = content.rstrip("\r\n").splitlines()
    if not raw_lines:
        msg = f"Evaluation dataset file is empty (0 lines): {path}"
        if raise_on_fatal:
            raise DatasetEmptyError(msg)
        return DatasetValidationResult(
            total_lines=0,
            is_valid=False,
            fatal_error=msg,
        )

    total_lines = len(raw_lines)
    valid_count = 0
    inconclusive_count = 0
    malformed_count = 0

    validated_lines: list[ValidatedLine] = []
    seen_case_ids: dict[str, int] = {}  # case_id -> 1-indexed line_number
    fatal_error: str | None = None

    for idx, line_str in enumerate(raw_lines, start=1):
        stripped = line_str.strip()

        # Empty or whitespace-only lines are flagged as malformed_input
        if not stripped:
            malformed_count += 1
            validated_lines.append(
                ValidatedLine(
                    source_line_number=idx,
                    validation_status="malformed_input",
                    case_id=None,
                    case=None,
                    error_details={"error": "EmptyLineError", "message": "Line is empty or whitespace only"},
                    raw_content=line_str[:200],
                )
            )
            continue

        # JSON parsing
        try:
            raw_obj = json.loads(line_str)
        except json.JSONDecodeError as jde:
            malformed_count += 1
            validated_lines.append(
                ValidatedLine(
                    source_line_number=idx,
                    validation_status="malformed_input",
                    case_id=None,
                    case=None,
                    error_details={
                        "error": "JSONDecodeError",
                        "message": str(jde),
                        "lineno": jde.lineno,
                        "colno": jde.colno,
                    },
                    raw_content=line_str[:200],
                )
            )
            continue

        if not isinstance(raw_obj, dict):
            malformed_count += 1
            validated_lines.append(
                ValidatedLine(
                    source_line_number=idx,
                    validation_status="malformed_input",
                    case_id=None,
                    case=None,
                    error_details={"error": "InvalidTypeError", "message": f"Expected JSON object, got {type(raw_obj).__name__}"},
                    raw_content=line_str[:200],
                )
            )
            continue

        raw_case_id: str | None = raw_obj.get("case_id") if isinstance(raw_obj.get("case_id"), str) else None

        # Pydantic schema validation
        try:
            case_instance = EvaluationCaseSchema.model_validate(raw_obj)
        except ValidationError as ve:
            malformed_count += 1
            validated_lines.append(
                ValidatedLine(
                    source_line_number=idx,
                    validation_status="malformed_input",
                    case_id=raw_case_id,
                    case=None,
                    error_details={"error": "ValidationError", "details": ve.errors()},
                    raw_content=line_str[:200],
                )
            )
            continue

        # Check for duplicate valid case_id
        if case_instance.case_id in seen_case_ids:
            first_seen_line = seen_case_ids[case_instance.case_id]
            msg = (
                f"Duplicate valid case_id '{case_instance.case_id}' detected at line {idx} "
                f"(first seen at line {first_seen_line})"
            )
            if raise_on_fatal:
                raise DuplicateCaseIDError(msg)
            fatal_error = msg
            malformed_count += 1
            validated_lines.append(
                ValidatedLine(
                    source_line_number=idx,
                    validation_status="malformed_input",
                    case_id=case_instance.case_id,
                    case=case_instance,
                    error_details={"error": "DuplicateCaseIDError", "message": msg},
                    raw_content=line_str[:200],
                )
            )
            continue

        seen_case_ids[case_instance.case_id] = idx

        # Distinguish inconclusive (valid syntax/schema but missing ground truth) vs valid
        if case_instance.expected_triage is None:
            inconclusive_count += 1
            validated_lines.append(
                ValidatedLine(
                    source_line_number=idx,
                    validation_status="inconclusive",
                    case_id=case_instance.case_id,
                    case=case_instance,
                    error_details=None,
                    raw_content=None,
                )
            )
        else:
            valid_count += 1
            validated_lines.append(
                ValidatedLine(
                    source_line_number=idx,
                    validation_status="valid",
                    case_id=case_instance.case_id,
                    case=case_instance,
                    error_details=None,
                    raw_content=None,
                )
            )

    is_valid = (malformed_count == 0 and fatal_error is None)

    return DatasetValidationResult(
        total_lines=total_lines,
        valid_cases_count=valid_count,
        inconclusive_count=inconclusive_count,
        malformed_count=malformed_count,
        lines=validated_lines,
        is_valid=is_valid,
        fatal_error=fatal_error,
    )

