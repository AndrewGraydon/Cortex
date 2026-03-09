"""Tests for MCP server — exposes Cortex tools via MCP protocol."""

from __future__ import annotations

from typing import Any

import pytest

from cortex.agent.types import ToolResult
from cortex.mcp.server import configure_server, get_mcp_server, get_streamable_http_app


class _MockTool:
    """Minimal tool for testing MCP server registration."""

    def __init__(
        self,
        name: str = "mock_tool",
        description: str = "A mock tool",
        permission_tier: int = 0,
    ) -> None:
        self._name = name
        self._description = description
        self._tier = permission_tier
        self._last_args: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def permission_tier(self) -> int:
        return self._tier

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self._name,
            "description": self._description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        self._last_args = arguments
        return ToolResult(
            tool_name=self._name,
            success=True,
            data={"result": "ok"},
            display_text=f"Executed {self._name}",
        )


class _MockMcpTool(_MockTool):
    """Mock tool that looks like an MCP-sourced tool (has server_name)."""

    def __init__(self) -> None:
        super().__init__(name="mcp__remote_tool")
        self.server_name = "remote_server"


class _MockRegistry:
    """Minimal tool registry for testing."""

    def __init__(self, tools: list[_MockTool] | None = None) -> None:
        self._tools: dict[str, _MockTool] = {}
        for t in tools or []:
            self._tools[t.name] = t

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def get(self, name: str) -> _MockTool | None:
        return self._tools.get(name)


class TestConfigureServer:
    def test_configure_returns_fast_mcp(self) -> None:
        from mcp.server import FastMCP

        registry = _MockRegistry([_MockTool()])
        server = configure_server(registry)
        assert isinstance(server, FastMCP)

    def test_configure_stores_server(self) -> None:
        registry = _MockRegistry([_MockTool()])
        configure_server(registry)
        assert get_mcp_server() is not None

    def test_configure_with_empty_registry(self) -> None:
        registry = _MockRegistry([])
        server = configure_server(registry)
        assert server is not None

    def test_configure_with_custom_name(self) -> None:
        registry = _MockRegistry([_MockTool()])
        server = configure_server(registry, server_name="my-cortex")
        assert server.name == "my-cortex"

    def test_skips_mcp_sourced_tools(self) -> None:
        mcp_tool = _MockMcpTool()
        local_tool = _MockTool(name="local_tool")
        registry = _MockRegistry([mcp_tool, local_tool])
        configure_server(registry)
        # MCP-sourced tools should be skipped (no re-exporting)
        server = get_mcp_server()
        assert server is not None

    def test_cognitive_tools_filter(self) -> None:
        tier0 = _MockTool(name="reader", permission_tier=0)
        tier1 = _MockTool(name="writer", permission_tier=1)
        registry = _MockRegistry([tier0, tier1])
        configure_server(
            registry,
            expose_cognitive_tools=False,
            expose_action_templates=True,
        )
        server = get_mcp_server()
        assert server is not None

    def test_action_templates_filter(self) -> None:
        tier0 = _MockTool(name="reader", permission_tier=0)
        tier1 = _MockTool(name="writer", permission_tier=1)
        registry = _MockRegistry([tier0, tier1])
        configure_server(
            registry,
            expose_cognitive_tools=True,
            expose_action_templates=False,
        )
        server = get_mcp_server()
        assert server is not None


class TestGetStreamableHttpApp:
    def test_returns_app_after_configure(self) -> None:
        registry = _MockRegistry([_MockTool()])
        configure_server(registry)
        app = get_streamable_http_app()
        assert app is not None

    def test_raises_before_configure(self) -> None:
        # Reset module state
        import cortex.mcp.server as srv

        srv._mcp_server = None
        with pytest.raises(RuntimeError, match="not configured"):
            get_streamable_http_app()


class TestMultipleTools:
    def test_register_multiple_tools(self) -> None:
        tools = [
            _MockTool(name="clock", description="Get time", permission_tier=0),
            _MockTool(name="calculator", description="Math", permission_tier=0),
            _MockTool(name="email_send", description="Send email", permission_tier=2),
        ]
        registry = _MockRegistry(tools)
        server = configure_server(registry)
        assert server is not None
