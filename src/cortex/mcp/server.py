"""MCP server — exposes Cortex tools to external MCP clients.

Uses the official MCP SDK's FastMCP server with Streamable HTTP transport,
mounted on the existing FastAPI application.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import FastMCP

logger = logging.getLogger(__name__)

# Module-level references — set via configure_server()
_tool_registry: Any = None
_mcp_server: FastMCP | None = None


def configure_server(
    tool_registry: Any,
    server_name: str = "cortex",
    expose_cognitive_tools: bool = True,
    expose_action_templates: bool = True,
) -> FastMCP:
    """Create and configure the MCP server with Cortex tools.

    Args:
        tool_registry: The Cortex ToolRegistry to expose.
        server_name: Server name for MCP identification.
        expose_cognitive_tools: Whether to expose read-only (Tier 0) tools.
        expose_action_templates: Whether to expose action (Tier 1+) tools.

    Returns:
        Configured FastMCP server instance.
    """
    global _tool_registry, _mcp_server  # noqa: PLW0603
    _tool_registry = tool_registry

    server = FastMCP(
        server_name,
        instructions="Cortex AI assistant tools.",
    )

    # Register each Cortex tool with the MCP server
    for tool_name in tool_registry.tool_names:
        tool = tool_registry.get(tool_name)
        if tool is None:
            continue

        tier = tool.permission_tier
        if tier == 0 and not expose_cognitive_tools:
            continue
        if tier >= 1 and not expose_action_templates:
            continue

        # Skip MCP-sourced tools to avoid re-exporting
        if hasattr(tool, "server_name"):
            continue

        _register_mcp_tool(server, tool)

    _mcp_server = server
    registered = sum(
        1
        for name in tool_registry.tool_names
        if not hasattr(tool_registry.get(name), "server_name")
    )
    logger.info("MCP server configured with up to %d tools", registered)
    return server


def _register_mcp_tool(server: FastMCP, tool: Any) -> None:
    """Register a single Cortex tool with the MCP server."""
    tool_name = tool.name
    tool_desc = tool.description

    def _make_handler(t: Any) -> Any:
        """Create a closure capturing the tool reference."""

        @server.tool(name=tool_name, description=tool_desc)
        async def mcp_tool_handler(**kwargs: Any) -> str:
            try:
                result = await t.execute(kwargs)
                if result.success:
                    return result.display_text or str(result.data)
                return f"Error: {result.error}"
            except Exception as e:
                logger.exception("MCP tool handler for %s failed", t.name)
                return f"Error: {e}"

        return mcp_tool_handler

    _make_handler(tool)


def get_mcp_server() -> FastMCP | None:
    """Get the configured MCP server instance."""
    return _mcp_server


def get_streamable_http_app() -> Any:
    """Get the ASGI app for Streamable HTTP transport.

    Mount this on FastAPI for MCP endpoint support.
    """
    if _mcp_server is None:
        msg = "MCP server not configured — call configure_server() first"
        raise RuntimeError(msg)
    return _mcp_server.streamable_http_app()
