from __future__ import annotations

import re
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from trustdesk.core.logging import get_logger
from trustdesk.models.knowledge import KBSection, KnowledgeDocument

logger = get_logger(__name__)

SUBCHUNK_CHAR_THRESHOLD = 1500


def _split_into_subchunks(text: str, max_chars: int = SUBCHUNK_CHAR_THRESHOLD) -> list[str]:
    """Splits text exceeding max_chars into deterministic sub-chunks on paragraph/sentence boundaries."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        p = paragraph.strip()
        if not p:
            continue

        if not current:
            if len(p) <= max_chars:
                current = p
            else:
                # Paragraph itself exceeds threshold: split on sentence boundaries
                sentences = re.split(r"(?<=[.!?])\s+", p)
                sub_current = ""
                for s in sentences:
                    s_clean = s.strip()
                    if not s_clean:
                        continue
                    if not sub_current:
                        sub_current = s_clean[:max_chars]
                    elif len(sub_current) + len(s_clean) + 1 <= max_chars:
                        sub_current = f"{sub_current} {s_clean}"
                    else:
                        chunks.append(sub_current)
                        sub_current = s_clean[:max_chars]
                if sub_current:
                    current = sub_current
        elif len(current) + len(p) + 2 <= max_chars:
            current = f"{current}\n\n{p}"
        else:
            chunks.append(current)
            current = p

    if current:
        chunks.append(current)

    return chunks if chunks else [text[:max_chars]]


def parse_markdown_sections(
    kb_id: str,
    raw_content: str,
    doc_title: str | None = None,
    max_chars: int = SUBCHUNK_CHAR_THRESHOLD,
) -> list[dict[str, Any]]:
    """Parses markdown raw content into structured sections based on '## ' headers.

    Preserves parent document title context in section_title so PostgreSQL full-text
    search captures policy domain keywords with weight 'A'.
    If a document contains no '## ' headers, treats the entire body as a single section {kb_id}#sec-0.
    Sub-chunks sections exceeding max_chars deterministically while preserving header context.
    """
    cleaned_content = raw_content.strip()
    if not cleaned_content:
        return []

    # Extract or fallback to top-level # title if doc_title not supplied
    if not doc_title:
        lines = cleaned_content.splitlines()
        if lines and lines[0].startswith("# "):
            doc_title = lines[0].lstrip("# ").strip()

    # Find all ## section headings
    heading_pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    matches = list(heading_pattern.finditer(cleaned_content))

    sections_data: list[dict[str, Any]] = []

    if not matches:
        # P3-EC-005: No ## headers present. Treat entire content as single section.
        title = doc_title or "Overview"
        lines = cleaned_content.splitlines()
        if lines and lines[0].startswith("# "):
            body = "\n".join(lines[1:]).strip() or title
        else:
            body = cleaned_content

        subchunks = _split_into_subchunks(body, max_chars=max_chars)
        for sub_idx, chunk_text in enumerate(subchunks):
            sec_id = f"{kb_id}#sec-0" if len(subchunks) == 1 else f"{kb_id}#sec-0-sub-{sub_idx}"
            sections_data.append({
                "section_id": sec_id,
                "kb_id": kb_id,
                "section_index": sub_idx,
                "section_title": title,
                "section_content": chunk_text,
            })
        return sections_data

    # Process each section under ## headings
    overall_sec_counter = 0

    for idx, match in enumerate(matches):
        raw_heading_title = match.group(1).strip()
        start_pos = match.end()
        end_pos = matches[idx + 1].start() if idx + 1 < len(matches) else len(cleaned_content)

        section_body = cleaned_content[start_pos:end_pos].strip()
        if not section_body:
            section_body = raw_heading_title

        # Preserve parent policy context in section title for FTS indexing
        full_section_title = f"{doc_title} — {raw_heading_title}" if doc_title else raw_heading_title

        subchunks = _split_into_subchunks(section_body, max_chars=max_chars)

        for sub_idx, chunk_text in enumerate(subchunks):
            if len(subchunks) == 1:
                sec_id = f"{kb_id}#sec-{idx}"
            else:
                sec_id = f"{kb_id}#sec-{idx}-sub-{sub_idx}"

            sections_data.append({
                "section_id": sec_id,
                "kb_id": kb_id,
                "section_index": overall_sec_counter,
                "section_title": full_section_title,
                "section_content": chunk_text,
            })
            overall_sec_counter += 1

    return sections_data


def derive_and_index_sections(session: Session, kb_id: str | None = None) -> int:
    """Derives sections for knowledge documents and persists them in kb_sections.

    Idempotent: removes pre-existing sections for target documents before inserting new sections.
    Returns total number of persisted sections.
    """
    query = select(KnowledgeDocument)
    if kb_id:
        query = query.where(KnowledgeDocument.kb_id == kb_id)

    documents = session.scalars(query).all()
    if not documents:
        logger.warning("No knowledge documents found for section derivation")
        return 0

    total_persisted = 0

    for doc in documents:
        parsed_sections = parse_markdown_sections(
            kb_id=doc.kb_id,
            raw_content=doc.raw_content,
            doc_title=doc.title,
        )

        # Clear existing sections for this document to guarantee idempotency and remove stale subchunks
        session.execute(delete(KBSection).where(KBSection.kb_id == doc.kb_id))

        for sec in parsed_sections:
            section_model = KBSection(
                section_id=sec["section_id"],
                kb_id=sec["kb_id"],
                section_index=sec["section_index"],
                section_title=sec["section_title"],
                section_content=sec["section_content"],
            )
            session.add(section_model)
            total_persisted += 1

    session.flush()
    logger.info(
        "Derived and persisted knowledge sections",
        extra={"document_count": len(documents), "total_sections": total_persisted},
    )
    return total_persisted
