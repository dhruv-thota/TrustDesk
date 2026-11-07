from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from trustdesk.core.config import settings
import trustdesk.core.database as db_mod
from trustdesk.core.database import get_db
from trustdesk.main import app


def _validate_test_db_isolation() -> str:
    """Verifies that DATABASE_URL_TEST is configured and points to an isolated test database."""
    test_url = settings.database_url_test
    dev_url = settings.database_url
    if not test_url:
        raise RuntimeError("DATABASE_URL_TEST is not configured or empty. Tests cannot run safely.")
    if test_url == dev_url:
        raise RuntimeError(
            f"DATABASE_URL_TEST matches DATABASE_URL ({test_url}). Aborting tests to protect development database."
        )

    parsed_test_url = make_url(test_url)
    parsed_dev_url = make_url(dev_url)

    test_db_name = parsed_test_url.database
    dev_db_name = parsed_dev_url.database

    if not test_db_name or not test_db_name.endswith("_test"):
        raise RuntimeError(
            f"Target test database '{test_db_name}' must end with '_test' to guarantee test isolation."
        )
    if test_db_name == dev_db_name:
        raise RuntimeError(
            f"Target test database '{test_db_name}' cannot be identical to development database '{dev_db_name}'."
        )

    return test_db_name


# Validate isolation immediately upon test discovery
TEST_DB_NAME = _validate_test_db_isolation()

# Set environment variable so subprocesses (CLI runner, worker, alembic) inherit the test database URL
os.environ["DATABASE_URL"] = settings.database_url_test

# Create dedicated session-level test engine and session factory bound to DATABASE_URL_TEST
session_test_engine = db_mod.get_engine(settings.database_url_test)
db_mod.engine = session_test_engine
db_mod.SessionFactory.configure(bind=session_test_engine)


@pytest.fixture(scope="session", autouse=True)
def enforce_test_database_session():
    """Session-wide fixture ensuring ALL test modules run strictly against the isolated test database."""
    # Verify physical connection
    with session_test_engine.connect() as conn:
        active_db = conn.execute(text("SELECT current_database();")).scalar()
        if active_db != TEST_DB_NAME:
            raise RuntimeError(f"Connected to '{active_db}', expected test database '{TEST_DB_NAME}'.")
        if active_db == "trustdesk":
            raise RuntimeError("CRITICAL: Connected directly to development database 'trustdesk'. Aborting.")

    yield session_test_engine


@pytest.fixture(autouse=True)
def guard_test_engine_binding():
    """Function-level fixture guaranteeing engine and SessionFactory remain bound to the test database

    even if an individual test module reconfigured or restored them during its own lifecycle.
    """
    if db_mod.engine is not session_test_engine:
        db_mod.engine = session_test_engine
        db_mod.SessionFactory.configure(bind=session_test_engine)

    # Ensure app dependency yields from test SessionFactory
    def _test_db_override():
        session = db_mod.SessionFactory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _test_db_override

    yield

    # Clean up overrides after test
    app.dependency_overrides.pop(get_db, None)
    if db_mod.engine is not session_test_engine:
        db_mod.engine = session_test_engine
        db_mod.SessionFactory.configure(bind=session_test_engine)
