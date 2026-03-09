"""Tool registry — loads tools and provides schemas for context assembly."""

from __future__ import annotations

import logging
from typing import Any

from cortex.agent.types import ToolCall, ToolResult
from cortex.reasoning.types import ToolSchema
from cortex.security.types import PermissionTier

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry of available tools.

    Tools are registered by name and provide schemas for prompt injection
    and handlers for execution.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}
        self._sources: dict[str, str] = {}  # tool_name -> source type

    def register(self, tool: Any, source: str = "python") -> None:
        """Register a tool. Tool must have name, description, permission_tier,
        get_schema(), and execute() attributes.

        Args:
            tool: Tool instance satisfying the Tool protocol.
            source: Tool source type — "python", "script", or "mcp".
        """
        name = tool.name
        if name in self._tools:
            logger.warning("Overwriting tool registration: %s", name)
        self._tools[name] = tool
        self._sources[name] = source
        logger.debug("Registered tool: %s (tier %d, source %s)", name, tool.permission_tier, source)

    def get(self, name: str) -> Any | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_schemas(self, names: list[str] | None = None) -> list[ToolSchema]:
        """Get tool schemas, optionally filtered by name.

        If names is None, returns all tool schemas.
        """
        tools = (
            self._tools.values()
            if names is None
            else [self._tools[n] for n in names if n in self._tools]
        )
        schemas = []
        for tool in tools:
            schema_dict = tool.get_schema()
            schemas.append(
                ToolSchema(
                    name=schema_dict.get("name", tool.name),
                    description=schema_dict.get("description", tool.description),
                    parameters=schema_dict.get("parameters", {}).get("properties", {}),
                )
            )
        return schemas

    def get_tier(self, name: str) -> PermissionTier:
        """Get the permission tier for a tool."""
        tool = self._tools.get(name)
        if tool is None:
            return PermissionTier.DANGER  # Unknown tools default to highest tier
        return PermissionTier(tool.permission_tier)

    async def execute(self, call: ToolCall) -> ToolResult:
        """Execute a tool call. Returns ToolResult."""
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(
                tool_name=call.name,
                success=False,
                error=f"Unknown tool: {call.name}",
            )
        try:
            result: ToolResult = await tool.execute(call.arguments)
            return result
        except Exception as e:
            logger.exception("Tool %s failed", call.name)
            return ToolResult(
                tool_name=call.name,
                success=False,
                error=str(e),
            )

    @property
    def tool_names(self) -> list[str]:
        """List of registered tool names."""
        return list(self._tools.keys())

    def get_source(self, name: str) -> str:
        """Get the source type for a tool ('python', 'script', or 'mcp')."""
        return self._sources.get(name, "python")

    def get_by_source(self, source: str) -> list[str]:
        """Get all tool names from a specific source."""
        return [n for n, s in self._sources.items() if s == source]

    def __len__(self) -> int:
        return len(self._tools)
