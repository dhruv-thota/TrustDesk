from __future__ import annotations

import pytest
from pydantic import ValidationError

from trustdesk.core.config import Settings
from trustdesk.core.redis import (
    check_redis_connection,
    get_redis_client,
    reset_redis_pool,
    sanitize_redis_url,
)


def test_settings_redis_defaults() -> None:
    """Verifies default Redis and RQ settings in Settings."""
    cfg = Settings(
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/trustdesk",
        database_url_test="postgresql+psycopg://postgres:postgres@localhost:5432/trustdesk_test",
    )
    assert cfg.redis_url == "redis://localhost:6379/0"
    assert cfg.rq_queue_name == "default"
    assert cfg.worker_stale_threshold_seconds == 60
    assert cfg.worker_heartbeat_timeout_seconds == 120


def test_settings_custom_redis_config() -> None:
    """Verifies that Redis and RQ configuration can be overridden."""
    cfg = Settings(
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/trustdesk",
        redis_url="redis://custom-host:6380/2",
        rq_queue_name="high_priority",
        worker_stale_threshold_seconds=90,
        worker_heartbeat_timeout_seconds=180,
    )
    assert cfg.redis_url == "redis://custom-host:6380/2"
    assert cfg.rq_queue_name == "high_priority"
    assert cfg.worker_stale_threshold_seconds == 90
    assert cfg.worker_heartbeat_timeout_seconds == 180


def test_settings_invalid_redis_url_raises_validation_error() -> None:
    """Verifies that an unsupported redis protocol raises ValidationError."""
    with pytest.raises(ValidationError):
        Settings(redis_url="http://localhost:6379/0")

    with pytest.raises(ValidationError):
        Settings(redis_url="postgres://localhost:5432/0")


def test_settings_invalid_thresholds_raise_validation_error() -> None:
    """Verifies that invalid threshold bounds raise ValidationError."""
    with pytest.raises(ValidationError):
        Settings(worker_stale_threshold_seconds=1)  # ge=5

    with pytest.raises(ValidationError):
        Settings(worker_heartbeat_timeout_seconds=2)  # ge=10


def test_sanitize_redis_url_masks_credentials() -> None:
    """Verifies that passwords embedded in Redis URLs are masked."""
    url = "redis://admin:super_secret_password_123@redis-cluster.internal:6379/0"
    sanitized = sanitize_redis_url(url)
    assert "super_secret_password_123" not in sanitized
    assert sanitized == "redis://admin:***@redis-cluster.internal:6379/0"


def test_get_redis_client_lazy_initialization() -> None:
    """Verifies that Redis client factory creates client lazily without connecting immediately."""
    reset_redis_pool()
    client = get_redis_client()
    assert client is not None
    assert client.connection_pool is not None
    reset_redis_pool()


def test_get_redis_client_custom_injection() -> None:
    """Verifies that client factory respects custom URL injection for testing."""
    custom_url = "redis://custom-test-host:6380/5"
    client = get_redis_client(redis_url=custom_url)
    assert client.connection_pool.connection_kwargs["host"] == "custom-test-host"
    assert client.connection_pool.connection_kwargs["port"] == 6380
    assert client.connection_pool.connection_kwargs["db"] == 5


def test_check_redis_connection_failure_handling() -> None:
    """Verifies that connection failures to an unreachable host raise ConnectionError cleanly."""
    # Port 6399 is unused and unreachable
    unreachable_client = get_redis_client(redis_url="redis://127.0.0.1:6399/0")
    with pytest.raises(ConnectionError) as exc_info:
        check_redis_connection(client=unreachable_client)
    assert "Unable to connect to Redis broker" in str(exc_info.value)

