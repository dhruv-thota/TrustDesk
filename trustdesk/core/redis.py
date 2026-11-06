from __future__ import annotations

import re
from typing import Any
import redis
from redis.connection import ConnectionPool

from trustdesk.core.config import settings
from trustdesk.core.logging import get_logger

logger = get_logger(__name__)

# Module-level connection pool cache (initialized lazily)
_redis_pool: ConnectionPool | None = None


def sanitize_redis_url(url: str) -> str:
    """Mask password credentials in a Redis URL for safe logging and error reporting."""
    # Matches patterns like redis://:password@host or redis://user:password@host
    return re.sub(r"://([^:@]+):([^@]+)@", r"://\1:***@", url)


def get_redis_pool(redis_url: str | None = None) -> ConnectionPool:
    """Get or lazily initialize the shared Redis connection pool."""
    global _redis_pool
    target_url = redis_url or settings.redis_url
    if _redis_pool is None or redis_url is not None:
        pool = ConnectionPool.from_url(
            target_url,
            decode_responses=False,
            max_connections=20,
        )
        if redis_url is None:
            _redis_pool = pool
        return pool
    return _redis_pool


def get_redis_client(
    redis_url: str | None = None,
    decode_responses: bool = False,
) -> redis.Redis:
    """Factory function providing a configured Redis client instance.

    Connections are not initiated at module import time; sockets are acquired lazily
    from the connection pool when commands are executed.
    Supports dependency injection via custom redis_url for testing.
    """
    target_url = redis_url or settings.redis_url
    if redis_url is not None:
        return redis.Redis.from_url(target_url, decode_responses=decode_responses)

    pool = get_redis_pool(target_url)
    return redis.Redis(connection_pool=pool, decode_responses=decode_responses)


def reset_redis_pool() -> None:
    """Disconnect and reset the shared connection pool (used for testing and teardown)."""
    global _redis_pool
    if _redis_pool is not None:
        try:
            _redis_pool.disconnect()
        except Exception:
            pass
        _redis_pool = None


def check_redis_connection(client: redis.Redis | None = None) -> bool:
    """Ping Redis to verify active connectivity without leaking credentials.

    Returns True if Redis responds with PONG.
    Raises ConnectionError with a sanitized message if the broker is unreachable.
    """
    r = client or get_redis_client()
    try:
        return bool(r.ping())
    except Exception as exc:
        logger.warning(
            "Redis connectivity check failed: %s",
            type(exc).__name__,
            extra={"error_type": type(exc).__name__},
        )
        raise ConnectionError(
            f"Unable to connect to Redis broker: {type(exc).__name__}"
        ) from exc

