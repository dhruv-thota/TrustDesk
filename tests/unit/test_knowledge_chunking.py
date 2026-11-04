from __future__ import annotations

import json
from pathlib import Path

import pytest

from trustdesk.services.knowledge_service import (
    SUBCHUNK_CHAR_THRESHOLD,
    parse_markdown_sections,
)


def test_parse_markdown_sections_heading_splitting() -> None:
    """Verifies markdown header splitting produces correct {kb_id}#sec-{index} IDs (P3-EV-001)."""
    raw_markdown = (
        "# Standard Return and Refund Policy\n\n"
        "## 1. Overview and Eligibility Window\n"
        "Customers may return eligible hardware products within 30 calendar days.\n\n"
        "## 2. Product Condition and Requirements\n"
        "Items must be returned in their original packaging, including all accessories.\n\n"
        "## 3. Refund Review and Human Approval\n"
        "Any refund action recommended by support automation must undergo human review."
    )

    sections = parse_markdown_sections(kb_id="KB-REFUND-001", raw_content=raw_markdown)

    assert len(sections) == 3

    assert sections[0]["section_id"] == "KB-REFUND-001#sec-0"
    assert sections[0]["kb_id"] == "KB-REFUND-001"
    assert sections[0]["section_index"] == 0
    assert "1. Overview and Eligibility Window" in sections[0]["section_title"]
    assert "Standard Return and Refund Policy" in sections[0]["section_title"]
    assert "30 calendar days" in sections[0]["section_content"]

    assert sections[1]["section_id"] == "KB-REFUND-001#sec-1"
    assert sections[1]["kb_id"] == "KB-REFUND-001"
    assert sections[1]["section_index"] == 1
    assert "2. Product Condition and Requirements" in sections[1]["section_title"]
    assert "original packaging" in sections[1]["section_content"]

    assert sections[2]["section_id"] == "KB-REFUND-001#sec-2"
    assert sections[2]["kb_id"] == "KB-REFUND-001"
    assert sections[2]["section_index"] == 2
    assert "3. Refund Review and Human Approval" in sections[2]["section_title"]
    assert "human review" in sections[2]["section_content"]


def test_parse_markdown_sections_no_subheaders() -> None:
    """Verifies that documents without '##' headers produce a single sec-0 section (P3-EC-005)."""
    raw_markdown = (
        "# General Information Notice\n\n"
        "This is an un-sectioned policy text providing broad terms of service without subheaders."
    )

    sections = parse_markdown_sections(kb_id="KB-GENERAL-001", raw_content=raw_markdown)

    assert len(sections) == 1
    assert sections[0]["section_id"] == "KB-GENERAL-001#sec-0"
    assert sections[0]["kb_id"] == "KB-GENERAL-001"
    assert sections[0]["section_index"] == 0
    assert sections[0]["section_title"] == "General Information Notice"
    assert "broad terms of service" in sections[0]["section_content"]


def test_parse_markdown_sections_subchunking_threshold() -> None:
    """Verifies that sections exceeding 1,500 characters are sub-chunked deterministically (P3-EV-002, P3-EC-009)."""
    # Create long section of ~2,400 characters under one header
    para1 = "Paragraph 1: " + ("Return requirements detail and eligibility criteria. " * 15)  # ~800 chars
    para2 = "Paragraph 2: " + ("Inspection standards and packaging condition checks. " * 15)   # ~800 chars
    para3 = "Paragraph 3: " + ("Final approval and review submission guidelines. " * 15)       # ~800 chars
    long_markdown = f"## Comprehensive Policy Rules\n\n{para1}\n\n{para2}\n\n{para3}"

    assert len(long_markdown) > SUBCHUNK_CHAR_THRESHOLD

    sections = parse_markdown_sections(
        kb_id="KB-LONG-001",
        raw_content=long_markdown,
        max_chars=SUBCHUNK_CHAR_THRESHOLD,
    )

    assert len(sections) > 1
    for idx, sec in enumerate(sections):
        assert sec["section_id"] == f"KB-LONG-001#sec-0-sub-{idx}"
        assert sec["kb_id"] == "KB-LONG-001"
        assert sec["section_title"] == "Comprehensive Policy Rules"
        assert len(sec["section_content"]) <= SUBCHUNK_CHAR_THRESHOLD
        assert sec["section_index"] == idx


def test_parse_markdown_empty_content() -> None:
    """Verifies empty or whitespace-only content produces zero sections cleanly."""
    assert parse_markdown_sections("KB-EMPTY-001", "") == []
    assert parse_markdown_sections("KB-EMPTY-002", "   \n\n  ") == []


def test_all_dataset_kb_documents_chunking() -> None:
    """Verifies chunking across all authoritative policy documents in data/kb_documents.json."""
    kb_file = Path("./data/kb_documents.json")
    with open(kb_file, "r", encoding="utf-8") as f:
        docs = json.load(f)

    all_sections = []
    for doc in docs:
        sections = parse_markdown_sections(doc["kb_id"], doc["raw_content"])
        all_sections.extend(sections)

    # Document section counts:
    # KB-REFUND-001 -> 3 sections
    # KB-WAR-002 -> 3 sections
    # KB-SHIPPING-001 -> 2 sections
    # KB-ADVERSARIAL-001 -> 1 section
    # Total = 9 sections
    assert len(all_sections) == 9

    # Verify all section IDs are unique and strictly formatted
    section_ids = [s["section_id"] for s in all_sections]
    assert len(section_ids) == len(set(section_ids))
    for sid in section_ids:
        assert "#sec-" in sid
