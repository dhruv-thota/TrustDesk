from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field


class PolicySectionMatch(BaseModel):
    """Represents a policy section retrieved by the search adapter."""

    model_config = ConfigDict(frozen=True)

    kb_id: str = Field(description="Parent policy identifier, e.g. KB-REFUND-001")
    section_id: str = Field(description="Deterministic section reference, e.g. KB-REFUND-001#sec-1")
    section_title: str = Field(description="Section heading or topic")
    content: str = Field(description="Body content of the section")
    relevance_score: float = Field(default=0.0, description="Computed ranking relevance score")


class CitationRef(BaseModel):
    """Citation reference within a generated draft."""

    model_config = ConfigDict(frozen=True)

    kb_id: str = Field(description="Parent policy identifier")
    section_id: str = Field(description="Cited section identifier")
    quoted_snippet: str | None = Field(default=None, description="Direct supporting snippet from section")


class ProvenanceResult(BaseModel):
    """Outcome of citation provenance validation."""

    model_config = ConfigDict(frozen=True)

    has_valid_provenance: bool
    invalid_citations: list[CitationRef] = Field(default_factory=list)
    insufficient_evidence: bool = False


class PolicyRetrievalInterface(ABC):
    """Abstract retrieval contract decoupling consumers from specific search backends."""

    @abstractmethod
    def search_policies(
        self,
        query: str | list[str],
        limit: int = 5,
    ) -> list[PolicySectionMatch]:
        """Retrieve matching policy sections for one or multiple search queries.

        Args:
            query: Single query string or list of query strings for multi-intent retrieval.
            limit: Maximum number of ranked sections to return (default: 5).

        Returns:
            List of unique PolicySectionMatch items ordered by relevance score descending.
        """
        pass

