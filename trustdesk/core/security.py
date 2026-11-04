from __future__ import annotations

import secrets
from typing import Any

from fastapi import Header, Request
from pydantic import BaseModel, ConfigDict, Field

from trustdesk.core.config import settings
from trustdesk.core.exceptions import AuthenticationError

DEMO_AGENT_IDENTITY: dict[str, str] = {
    "agent_id": "demo-agent-001",
    "name": "Demo Support Agent",
    "role": "agent",
}


class AgentIdentity(BaseModel):
    """Authenticated agent identity representation."""

    model_config = ConfigDict(frozen=True)

    agent_id: str = Field(description="Unique internal agent identifier")
    name: str = Field(description="Display name of the support agent")
    role: str = Field(default="agent", description="Authorization role")


def verify_demo_token(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> AgentIdentity:
    """FastAPI dependency verifying incoming bearer token against server demo secret.

    Maps valid tokens server-side to the fixed internal demo agent identity.
    Client-supplied headers attempting to override identity (e.g. X-Agent-ID) are ignored.
    """
    if not authorization:
        raise AuthenticationError("Missing Authorization header.")

    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthenticationError("Invalid Authorization header format. Expected 'Bearer <token>'.")

    token = parts[1]
    expected_token = settings.trustdesk_demo_token

    if not secrets.compare_digest(token, expected_token):
        raise AuthenticationError("Invalid bearer token.")

    return AgentIdentity(**DEMO_AGENT_IDENTITY)

