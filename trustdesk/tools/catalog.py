from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from trustdesk.core.logging import get_logger

logger = get_logger(__name__)

# Strict architectural boundary: ONLY start_refund_review is an allowed operational action in MVP
ALLOWED_OPERATIONAL_ACTIONS: frozenset[str] = frozenset({"start_refund_review"})


class ToolDefinition(BaseModel):
    """Registered tool specification in the TrustDesk catalog."""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., description="Unique tool name")
    description: str = Field(..., description="Tool description")
    parameters: dict[str, Any] = Field(default_factory=dict, description="JSON schema for tool parameters")
    is_sensitive: bool = Field(default=False, description="Whether tool requires human authorization")
    is_supported: bool = Field(default=True, description="Whether tool is enabled for execution in TrustDesk")
    in_scope: bool = Field(default=True, description="Whether tool falls within approved architectural scope")


class ToolRegistry:
    """In-memory tool catalog registry enforcing TrustDesk's architectural boundaries."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool_data: dict[str, Any]) -> ToolDefinition:
        """Registers a tool definition, applying scope enforcement."""
        name = tool_data["name"]

        # Scope enforcement rule (P1-EC-007, U-013):
        # If the tool is an operational/sensitive action other than start_refund_review,
        # it MUST be marked is_supported=False and in_scope=False.
        is_sensitive = tool_data.get("is_sensitive", False)
        declared_supported = tool_data.get("is_supported", True)

        if is_sensitive and name not in ALLOWED_OPERATIONAL_ACTIONS:
            logger.warning(
                "Enforcing architectural boundary on tool '%s': marking as unsupported/out-of-scope.",
                name,
            )
            is_supported = False
            in_scope = False
        else:
            is_supported = declared_supported and (not is_sensitive or name in ALLOWED_OPERATIONAL_ACTIONS)
            in_scope = tool_data.get("in_scope", True) and (not is_sensitive or name in ALLOWED_OPERATIONAL_ACTIONS)

        tool_def = ToolDefinition(
            name=name,
            description=tool_data.get("description", ""),
            parameters=tool_data.get("parameters", {}),
            is_sensitive=is_sensitive,
            is_supported=is_supported,
            in_scope=in_scope,
        )
        self._tools[name] = tool_def
        return tool_def

    def load_from_file(self, file_path: Path | str) -> list[ToolDefinition]:
        """Loads and registers tools from a tool catalog JSON file."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Tool catalog file not found at: {path}")

        with open(path, "r", encoding="utf-8") as f:
            catalog_data = json.load(f)

        if not isinstance(catalog_data, list):
            raise ValueError(f"Tool catalog in {path} must contain a list of tool objects.")

        results: list[ToolDefinition] = []
        for item in catalog_data:
            tool = self.register(item)
            results.append(tool)

        logger.info(
            "Registered %d tools from catalog. Active operational actions: %s",
            len(results),
            [t.name for t in results if t.is_sensitive and t.is_supported],
        )
        return results

    def get(self, name: str) -> ToolDefinition | None:
        """Lookup a registered tool by name."""
        return self._tools.get(name)

    def get_all(self) -> list[ToolDefinition]:
        """Retrieve all registered tools."""
        return list(self._tools.values())

    def get_active_operational_tools(self) -> list[ToolDefinition]:
        """Retrieve all operational actions that are enabled and supported in TrustDesk.

        Per TrustDesk specifications, this must strictly contain ONLY start_refund_review.
        """
        return [t for t in self._tools.values() if t.is_sensitive and t.is_supported]

    def clear(self) -> None:
        """Reset the registry."""
        self._tools.clear()


registry = ToolRegistry()

