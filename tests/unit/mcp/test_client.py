"""Tests for MCP client manager — config loading, tool discovery, lifecycle."""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex.mcp.client import McpClientManager
from cortex.mcp.types import McpServerEntry, McpToolOverride


class TestConfigLoading:
    def test_load_empty_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text("servers: []\n")
        mgr = McpClientManager(servers_config=str(config_file))
        entries = mgr.load_config()
        assert entries == []

    def test_load_nonexistent_config(self) -> None:
        mgr = McpClientManager(servers_config="/nonexistent/path.yaml")
        entries = mgr.load_config()
        assert entries == []

    def test_load_single_server(self, tmp_path: Path) -> None:
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text(
            """
servers:
  - name: homeassistant
    url: "http://ha.local:8123/mcp"
    transport: streamable_http
    timeout_seconds: 10
    tool_prefix: ha
    default_permission_tier: 1
    enabled: true
"""
        )
        mgr = McpClientManager(servers_config=str(config_file))
        entries = mgr.load_config()
        assert len(entries) == 1
        assert entries[0].name == "homeassistant"
        assert entries[0].url == "http://ha.local:8123/mcp"
        assert entries[0].transport == "streamable_http"
        assert entries[0].timeout_seconds == 10
        assert entries[0].tool_prefix == "ha"
        assert entries[0].default_permission_tier == 1
        assert entries[0].enabled is True

    def test_load_multiple_servers(self, tmp_path: Path) -> None:
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text(
            """
servers:
  - name: ha
    url: "http://ha.local/mcp"
  - name: n8n
    url: "http://n8n.local/mcp"
"""
        )
        mgr = McpClientManager(servers_config=str(config_file))
        entries = mgr.load_config()
        assert len(entries) == 2
        assert entries[0].name == "ha"
        assert entries[1].name == "n8n"

    def test_load_with_tool_overrides(self, tmp_path: Path) -> None:
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text(
            """
servers:
  - name: ha
    url: "http://ha.local/mcp"
    tool_overrides:
      get_lights:
        triggers:
          - 'lights?\\s+status'
        keywords: [light, lamp]
        permission_tier: 0
"""
        )
        mgr = McpClientManager(servers_config=str(config_file))
        entries = mgr.load_config()
        assert len(entries) == 1
        assert "get_lights" in entries[0].tool_overrides
        override = entries[0].tool_overrides["get_lights"]
        assert override.permission_tier == 0
        assert "light" in override.keywords

    def test_default_tool_prefix_from_name(self, tmp_path: Path) -> None:
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text(
            """
servers:
  - name: myserver
    url: "http://localhost/mcp"
"""
        )
        mgr = McpClientManager(servers_config=str(config_file))
        entries = mgr.load_config()
        assert entries[0].tool_prefix == "myserver"

    def test_default_permission_tier(self, tmp_path: Path) -> None:
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text(
            """
servers:
  - name: test
    url: "http://localhost/mcp"
"""
        )
        mgr = McpClientManager(servers_config=str(config_file), default_permission_tier=1)
        entries = mgr.load_config()
        assert entries[0].default_permission_tier == 1

    def test_disabled_server(self, tmp_path: Path) -> None:
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text(
            """
servers:
  - name: disabled
    url: "http://localhost/mcp"
    enabled: false
"""
        )
        mgr = McpClientManager(servers_config=str(config_file))
        entries = mgr.load_config()
        assert entries[0].enabled is False

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text("{{invalid yaml")
        mgr = McpClientManager(servers_config=str(config_file))
        entries = mgr.load_config()
        assert entries == []

    def test_servers_stored_in_manager(self, tmp_path: Path) -> None:
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text(
            """
servers:
  - name: srv1
    url: "http://localhost/mcp"
"""
        )
        mgr = McpClientManager(servers_config=str(config_file))
        mgr.load_config()
        assert "srv1" in mgr.servers


class TestConnectionLifecycle:
    async def test_connect_unknown_server(self) -> None:
        mgr = McpClientManager()
        result = await mgr.connect("nonexistent")
        assert result is False

    async def test_connect_disabled_server(self, tmp_path: Path) -> None:
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text(
            """
servers:
  - name: disabled
    url: "http://localhost/mcp"
    enabled: false
"""
        )
        mgr = McpClientManager(servers_config=str(config_file))
        mgr.load_config()
        result = await mgr.connect("disabled")
        assert result is False

    async def test_connected_servers_empty(self) -> None:
        mgr = McpClientManager()
        assert mgr.connected_servers == []

    async def test_disconnect_unknown_server(self) -> None:
        mgr = McpClientManager()
        # Should not raise
        await mgr.disconnect("nonexistent")

    async def test_disconnect_all_empty(self) -> None:
        mgr = McpClientManager()
        # Should not raise
        await mgr.disconnect_all()


class TestToolDiscovery:
    async def test_discover_tools_not_connected(self) -> None:
        mgr = McpClientManager()
        tools = await mgr.discover_tools("unknown")
        assert tools == []

    async def test_discover_all_tools_empty(self) -> None:
        mgr = McpClientManager()
        tools = await mgr.discover_all_tools()
        assert tools == []


class TestHealthCheck:
    async def test_health_check_not_connected(self) -> None:
        mgr = McpClientManager()
        assert await mgr.health_check("unknown") is False

    async def test_health_check_all_empty(self) -> None:
        mgr = McpClientManager()
        results = await mgr.health_check_all()
        assert results == {}


class TestCallTool:
    async def test_call_tool_not_connected(self) -> None:
        mgr = McpClientManager()
        with pytest.raises(ConnectionError, match="not connected"):
            await mgr.call_tool("unknown", "tool", {})


class TestServerEntry:
    def test_defaults(self) -> None:
        entry = McpServerEntry(name="test", url="http://localhost/mcp")
        assert entry.transport == "streamable_http"
        assert entry.timeout_seconds == 5
        assert entry.tool_prefix == "test"
        assert entry.default_permission_tier == 2
        assert entry.enabled is True

    def test_custom_prefix(self) -> None:
        entry = McpServerEntry(
            name="homeassistant",
            url="http://localhost/mcp",
            tool_prefix="ha",
        )
        assert entry.tool_prefix == "ha"

    def test_empty_prefix_defaults_to_name(self) -> None:
        entry = McpServerEntry(name="myserver", url="http://localhost/mcp")
        assert entry.tool_prefix == "myserver"


class TestToolOverride:
    def test_defaults(self) -> None:
        override = McpToolOverride()
        assert override.triggers == []
        assert override.keywords == []
        assert override.permission_tier is None

    def test_with_values(self) -> None:
        override = McpToolOverride(
            triggers=[r"toggle\s+lights?"],
            keywords=["light", "lamp"],
            permission_tier=0,
        )
        assert len(override.triggers) == 1
        assert override.permission_tier == 0
