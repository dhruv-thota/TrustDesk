from __future__ import annotations

import pytest
import redis
from rq import Queue

from trustdesk.core.config import settings
from trustdesk.core.redis import (
    check_redis_connection,
    get_redis_client,
    reset_redis_pool,
)


def test_live_redis_connectivity_and_ping() -> None:
    """Verifies that Redis responds to PING on configured settings (Partial EG-P7-01)."""
    reset_redis_pool()
    client = get_redis_client()
    assert client.ping() is True
    assert check_redis_connection(client=client) is True


def test_rq_queue_initialization_with_redis_client() -> None:
    """Verifies that an RQ Queue can be instantiated using the Redis client factory."""
    client = get_redis_client()
    queue = Queue(name=settings.rq_queue_name, connection=client)
    assert queue.name == "default"
    assert queue.connection is client
    # Verify queue length query executes against broker
    assert isinstance(queue.count, int)


def test_redis_unavailable_handling_infrastructure_portion() -> None:
    """Verifies that an invalid Redis host raises ConnectionError cleanly (Partial P7-EC-001)."""
    unreachable_client = get_redis_client(redis_url="redis://127.0.0.1:6399/0")
    with pytest.raises(ConnectionError) as exc_info:
        check_redis_connection(client=unreachable_client)
    assert "Unable to connect to Redis broker" in str(exc_info.value)

