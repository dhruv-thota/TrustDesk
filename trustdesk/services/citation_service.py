from __future__ import annotations

from typing import Sequence

from trustdesk.core.logging import get_logger
from trustdesk.services.retrieval.base import CitationRef, PolicySectionMatch, ProvenanceResult

logger = get_logger(__name__)


def validate_citation_provenance(
    cited_sections: Sequence[CitationRef],
    retrieved_sections: Sequence[PolicySectionMatch],
) -> ProvenanceResult:
    """Validates that every cited policy section exists within the retrieved evidence set.

    Level 1 Citation Provenance Rule:
    - If evidence set is empty, insufficient_evidence is True.
    - If citation list is empty, has_valid_provenance is True (no claims to invalidate).
    - If any cited (kb_id, section_id) pair was not retrieved, has_valid_provenance is False,
      and invalid references are recorded in invalid_citations.
    """
    insufficient_evidence = len(retrieved_sections) == 0

    if not cited_sections:
        return ProvenanceResult(
            has_valid_provenance=True,
            invalid_citations=[],
            insufficient_evidence=insufficient_evidence,
        )

    # Build lookup set of authorized (kb_id, section_id) pairs
    retrieved_set = {(m.kb_id, m.section_id) for m in retrieved_sections}

    invalid_citations: list[CitationRef] = []

    for citation in cited_sections:
        pair = (citation.kb_id, citation.section_id)
        if pair not in retrieved_set:
            invalid_citations.append(citation)

    has_valid_provenance = len(invalid_citations) == 0

    if not has_valid_provenance:
        logger.warning(
            "Citation provenance validation failed",
            extra={
                "invalid_count": len(invalid_citations),
                "invalid_sections": [c.section_id for c in invalid_citations],
            },
        )

    return ProvenanceResult(
        has_valid_provenance=has_valid_provenance,
        invalid_citations=invalid_citations,
        insufficient_evidence=insufficient_evidence,
    )

