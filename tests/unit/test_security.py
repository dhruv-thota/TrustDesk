from __future__ import annotations

import pytest
from starlette.requests import Request

from trustdesk.core.config import settings
from trustdesk.core.exceptions import AuthenticationError
from trustdesk.core.security import DEMO_AGENT_IDENTITY, AgentIdentity, verify_demo_token


def _make_dummy_request(headers: dict[str, str] | None = None) -> Request:
    """Helper to construct dummy Starlette request for unit testing dependencies."""
    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/tickets",
        "headers": raw_headers,
    }
    return Request(scope)


def test_verify_demo_token_valid() -> None:
    """Verifies that a valid bearer token authenticates and binds to server identity (P2-EV-001)."""
    valid_header = f"Bearer {settings.trustdesk_demo_token}"
    req = _make_dummy_request({"Authorization": valid_header})
    identity = verify_demo_token(request=req, authorization=valid_header)

    assert isinstance(identity, AgentIdentity)
    assert identity.agent_id == DEMO_AGENT_IDENTITY["agent_id"]
    assert identity.name == DEMO_AGENT_IDENTITY["name"]
    assert identity.role == "agent"


def test_verify_demo_token_missing() -> None:
    """Verifies that missing Authorization header raises AuthenticationError (P2-EV-002, P2-EC-001)."""
    req = _make_dummy_request()
    with pytest.raises(AuthenticationError) as exc_info:
        verify_demo_token(request=req, authorization=None)

    assert exc_info.value.status_code == 401
    assert exc_info.value.error_code == "UNAUTHORIZED"
    assert "Missing Authorization header" in exc_info.value.message


def test_verify_demo_token_invalid_secret() -> None:
    """Verifies that incorrect token value is rejected with 401 (P2-EV-003, P2-EC-001)."""
    invalid_header = "Bearer wrong_token_value_xyz"
    req = _make_dummy_request({"Authorization": invalid_header})
    with pytest.raises(AuthenticationError) as exc_info:
        verify_demo_token(request=req, authorization=invalid_header)

    assert exc_info.value.status_code == 401
    assert exc_info.value.error_code == "UNAUTHORIZED"
    assert "Invalid bearer token" in exc_info.value.message


def test_verify_demo_token_malformed_scheme() -> None:
    """Verifies that non-Bearer authorization scheme is rejected (P2-EC-001)."""
    bad_header = "Basic dXNlcjpwYXNz"
    req = _make_dummy_request({"Authorization": bad_header})
    with pytest.raises(AuthenticationError) as exc_info:
        verify_demo_token(request=req, authorization=bad_header)

    assert exc_info.value.status_code == 401
    assert "Expected 'Bearer <token>'" in exc_info.value.message


def test_verify_demo_token_empty_token() -> None:
    """Verifies that Bearer header without token string is rejected (P2-EC-001)."""
    bad_header = "Bearer   "
    req = _make_dummy_request({"Authorization": bad_header})
    with pytest.raises(AuthenticationError) as exc_info:
        verify_demo_token(request=req, authorization=bad_header)

    assert exc_info.value.status_code == 401


def test_verify_demo_token_identity_tampering_immunity() -> None:
    """Verifies that client-supplied agent headers cannot override server identity (P2-EV-004, P2-EC-004)."""
    valid_header = f"Bearer {settings.trustdesk_demo_token}"
    tampering_headers = {
        "Authorization": valid_header,
        "X-Agent-ID": "forged-agent-999",
        "X-Agent-Role": "administrator",
    }
    req = _make_dummy_request(tampering_headers)
    identity = verify_demo_token(request=req, authorization=valid_header)

    assert identity.agent_id == "demo-agent-001"
    assert identity.agent_id != "forged-agent-999"
    assert identity.role == "agent"
    assert identity.role != "administrator"


def test_verify_demo_token_malformed_header_injection() -> None:
    """Verifies that injection attempts in Authorization header fail safely (P2-EC-009)."""
    malicious_header = "Bearer \r\nDROP TABLE tickets; --"
    req = _make_dummy_request({"Authorization": malicious_header})
    with pytest.raises(AuthenticationError) as exc_info:
        verify_demo_token(request=req, authorization=malicious_header)

    assert exc_info.value.status_code == 401
    assert exc_info.value.error_code == "UNAUTHORIZED"

