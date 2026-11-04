from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from trustdesk.core.config import settings
from trustdesk.core.logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy 2.0 models."""
    pass


def get_engine(database_url: str | None = None) -> Any:
    """Create a configured SQLAlchemy engine."""
    url = database_url or settings.database_url
    engine_kwargs: dict[str, Any] = {
        "echo": settings.log_level == "DEBUG",
        "pool_pre_ping": True,
    }

    # SQLite-specific connection parameters for testing
    if url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # PostgreSQL pool configuration
        engine_kwargs["pool_size"] = 10
        engine_kwargs["max_overflow"] = 20

    return create_engine(url, **engine_kwargs)


engine = get_engine()
SessionFactory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for yielding database sessions."""
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def get_db_session(custom_engine: Any | None = None) -> Generator[Session, None, None]:
    """Context manager for standalone database session transactions."""
    factory = sessionmaker(bind=custom_engine, autoflush=False, autocommit=False, expire_on_commit=False) if custom_engine else SessionFactory
    session = factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database_connection(custom_session: Session | None = None) -> dict[str, str]:
    """Executes a lightweight ping (SELECT 1) to verify database connectivity.

    Returns:
        dict: {"status": "healthy", "database": "connected"} or raises Exception.
    """
    if custom_session is not None:
        custom_session.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}

    with get_db_session() as session:
        session.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}

