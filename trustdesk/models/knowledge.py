from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Computed, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from trustdesk.core.database import Base


class KnowledgeDocument(Base):
    """Knowledge document entity preserving original policy identifiers and raw content."""

    __tablename__ = "kb_documents"

    kb_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        comment="Original verbatim dataset identifier (e.g. KB-REFUND-001, KB-ADVERSARIAL-001)",
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    sections: Mapped[list[KBSection]] = relationship(
        "KBSection",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="KBSection.section_index",
    )

    def __repr__(self) -> str:
        return f"<KnowledgeDocument kb_id={self.kb_id!r} category={self.category!r}>"


class KBSection(Base):
    """Derived knowledge base section with precomputed full-text search vector."""

    __tablename__ = "kb_sections"

    section_id: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
        comment="Deterministic section reference formatted as {kb_id}#sec-{index}",
    )
    kb_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("kb_documents.kb_id", ondelete="CASCADE"),
        nullable=False,
    )
    section_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section_title: Mapped[str] = mapped_column(String(255), nullable=False)
    section_content: Mapped[str] = mapped_column(Text, nullable=False)
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR().with_variant(Text, "sqlite"),
        Computed(
            "setweight(to_tsvector('english', coalesce(section_title, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(section_content, '')), 'B')",
            persisted=True,
        ),
        nullable=True,
    )

    document: Mapped[KnowledgeDocument] = relationship("KnowledgeDocument", back_populates="sections")

    __table_args__ = (
        Index("idx_kb_sections_kb_id", "kb_id"),
        Index("idx_kb_sections_fts", "search_vector", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<KBSection section_id={self.section_id!r} kb_id={self.kb_id!r} section_index={self.section_index}>"
