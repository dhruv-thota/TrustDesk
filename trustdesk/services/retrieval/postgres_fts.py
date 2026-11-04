from __future__ import annotations

from typing import Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from trustdesk.core.logging import get_logger
from trustdesk.services.retrieval.base import PolicyRetrievalInterface, PolicySectionMatch

logger = get_logger(__name__)


class PostgresFtsRetrievalAdapter(PolicyRetrievalInterface):
    """PostgreSQL Full-Text Search adapter using plainto_tsquery and ts_rank_cd."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def search_policies(
        self,
        query: str | list[str],
        limit: int = 5,
    ) -> list[PolicySectionMatch]:
        """Retrieve matching policy sections using PostgreSQL full-text search.

        Supports single or multiple explicit queries, merges matches across queries,
        deduplicates by section_id, and ranks results deterministically.
        """
        if limit <= 0:
            limit = 5

        # Normalize to list of clean query strings
        if isinstance(query, str):
            raw_queries = [query]
        elif isinstance(query, Sequence):
            raw_queries = list(query)
        else:
            return []

        clean_queries = [q.strip() for q in raw_queries if isinstance(q, str) and q.strip()]
        if not clean_queries:
            return []

        query_sql = text("""
            SELECT 
                kb_id, 
                section_id, 
                section_title, 
                section_content,
                ts_rank_cd(search_vector, plainto_tsquery('english', :search_query)) AS relevance_score
            FROM kb_sections
            WHERE search_vector @@ plainto_tsquery('english', :search_query)
            ORDER BY relevance_score DESC
            LIMIT :query_limit;
        """)

        merged_by_id: dict[str, PolicySectionMatch] = {}

        for search_term in clean_queries:
            rows = self.session.execute(
                query_sql,
                {"search_query": search_term, "query_limit": limit},
            ).fetchall()

            for row in rows:
                match = PolicySectionMatch(
                    kb_id=row.kb_id,
                    section_id=row.section_id,
                    section_title=row.section_title,
                    content=row.section_content,
                    relevance_score=float(row.relevance_score),
                )
                existing = merged_by_id.get(match.section_id)
                if existing is None or match.relevance_score > existing.relevance_score:
                    merged_by_id[match.section_id] = match

        if not merged_by_id:
            return []

        # Sort deterministically: highest relevance score first, then section_id ascending
        sorted_matches = sorted(
            merged_by_id.values(),
            key=lambda m: (-m.relevance_score, m.section_id),
        )

        return sorted_matches[:limit]

