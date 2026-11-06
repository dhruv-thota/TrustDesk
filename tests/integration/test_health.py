from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from trustdesk.api.v1.health import health_check
from trustdesk.core.database import get_db
from trustdesk.main import app

client = TestClient(app)


def test_health_check_healthy() -> None:
    """Verifies that GET /api/v1/health returns HTTP 200 and healthy status (P1-EV-010)."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


def test_health_check_database_disconnected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that GET /api/v1/health returns HTTP 503 when the database is unreachable (P1-EV-011, P1-EC-008)."""

    def mock_failing_db():
        # Session pointing to an invalid database endpoint with bounded 1s timeout
        broken_engine = create_engine(
            "postgresql+psycopg://invalid_user:invalid_pass@127.0.0.1:54999/nonexistent",
            connect_args={"connect_timeout": 1},
        )
        BrokenSession = sessionmaker(bind=broken_engine)
        session = BrokenSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = mock_failing_db
    try:
        response = client.get("/api/v1/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "disconnected"
    finally:
        app.dependency_overrides.clear()

