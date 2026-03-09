"""MCP tool wrapper — adapts MCP-discovered tools to the Cortex Tool protocol."""

from __future__ import annotations

import logging
from typing import Any

from cortex.agent.types import ToolResult
from cortex.mcp.types import McpToolInfo

logger = logging.getLogger(__name__)


class McpToolWrapper:
    """Wraps an MCP tool so it satisfies the Cortex Tool protocol.

    When executed, delegates to the MCP client session to call the remote tool.
    """

    def __init__(
        self,
        info: McpToolInfo,
        call_fn: Any = None,
    ) -> None:
        self._info = info
        self._call_fn = call_fn  # async callable: (server_name, tool_name, arguments) -> result

    @property
    def name(self) -> str:
        return self._info.prefixed_name

    @property
    def description(self) -> str:
        return self._info.description

    @property
    def permission_tier(self) -> int:
        return self._info.permission_tier

    @property
    def server_name(self) -> str:
        return self._info.server_name

    @property
    def original_name(self) -> str:
        return self._info.original_name

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self._info.prefixed_name,
            "description": self._info.description,
            "parameters": self._info.input_schema,
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if self._call_fn is None:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="MCP client not connected.",
            )

        try:
            result = await self._call_fn(
                self._info.server_name,
                self._info.original_name,
                arguments,
            )
            return ToolResult(
                tool_name=self.name,
                success=True,
                data=result,
                display_text=(
                    str(result.get("text", ""))[:100]
                    if isinstance(result, dict)
                    else str(result)[:100]
                ),
            )
        except Exception as e:
            logger.exception("MCP tool %s failed", self.name)
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(e),
            )
