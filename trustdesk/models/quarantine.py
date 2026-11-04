from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column

from trustdesk.core.database import Base


class QuarantinedRecord(Base):
    """Audit entity for records rejected or quarantined during ingestion.

    Specifically captures records violating mandatory parent constraints (e.g. ticket
    referencing a non-existent customer_id) to prevent silent data discard while
    maintaining strict relational integrity.
    """

    __tablename__ = "quarantined_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_type: Mapped[str] = mapped_column(String(32), nullable=False)
    record_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<QuarantinedRecord id={self.id} type={self.record_type!r} record_id={self.record_id!r}>"

