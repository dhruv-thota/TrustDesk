from __future__ import annotations

import pytest
from pydantic import ValidationError

from trustdesk.core.config import Settings


def test_settings_default_values() -> None:
    """Verifies default configuration values and types (P1-EV-001)."""
    cfg = Settings(
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/trustdesk",
        database_url_test="postgresql+psycopg://postgres:postgres@localhost:5432/trustdesk_test",
    )
    assert cfg.environment in {"development", "test", "production"}
    assert cfg.log_level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    assert cfg.trustdesk_demo_token == "demo_secret_token_123"
    assert cfg.app_port == 8000
    assert cfg.app_host == "0.0.0.0"


def test_settings_custom_values() -> None:
    """Verifies configuration overriding via keyword arguments or environment variables (P1-EV-001)."""
    cfg = Settings(
        database_url="postgresql+psycopg://user:pass@db:5432/custom_db",
        trustdesk_demo_token="super_secret_token_abc",
        log_level="DEBUG",
        environment="test",
        app_port=9000,
    )
    assert cfg.database_url == "postgresql+psycopg://user:pass@db:5432/custom_db"
    assert cfg.trustdesk_demo_token == "super_secret_token_abc"
    assert cfg.log_level == "DEBUG"
    assert cfg.environment == "test"
    assert cfg.app_port == 9000


def test_settings_invalid_log_level_raises_validation_error() -> None:
    """Verifies that an unsupported log_level string raises ValidationError (P1-EV-001)."""
    with pytest.raises(ValidationError):
        Settings(log_level="VERBOSE_INVALID")


def test_settings_invalid_database_url_raises_validation_error() -> None:
    """Verifies that a non-database protocol URL raises ValidationError (P1-EV-001)."""
    with pytest.raises(ValidationError):
        Settings(database_url="mysql://root:root@localhost:3306/db")

