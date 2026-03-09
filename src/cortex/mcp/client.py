"""MCP client manager — discovers and connects to external MCP servers.

Loads server definitions from mcp_servers.yaml, connects via Streamable HTTP
or stdio transport, discovers tools, and registers them with the Cortex
ToolRegistry as McpToolWrapper instances.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from cortex.mcp.tool_wrapper import McpToolWrapper
from cortex.mcp.types import McpServerEntry, McpToolInfo, McpToolOverride

logger = logging.getLogger(__name__)


class McpClientManager:
    """Manages connections to external MCP servers.

    Responsibilities:
    - Load server definitions from YAML config
    - Connect to each enabled server
    - Discover tools via list_tools()
    - Create McpToolWrapper instances for registration
    - Handle reconnection and health checks
    """

    def __init__(
        self,
        servers_config: str = "config/mcp_servers.yaml",
        connect_timeout: int = 5,
        default_permission_tier: int = 2,
    ) -> None:
        self._servers_config = servers_config
        self._connect_timeout = connect_timeout
        self._default_permission_tier = default_permission_tier
        self._servers: dict[str, McpServerEntry] = {}
        self._sessions: dict[str, Any] = {}  # server_name -> ClientSession
        self._connected: set[str] = set()

    @property
    def servers(self) -> dict[str, McpServerEntry]:
        return dict(self._servers)

    @property
    def connected_servers(self) -> list[str]:
        return list(self._connected)

    def load_config(self, config_path: str | None = None) -> list[McpServerEntry]:
        """Load MCP server definitions from YAML config."""
        path = Path(config_path or self._servers_config)
        if not path.exists():
            logger.info("No MCP servers config at %s", path)
            return []

        try:
            raw = yaml.safe_load(path.read_text()) or {}
        except Exception:
            logger.exception("Failed to load MCP servers config from %s", path)
            return []

        entries: list[McpServerEntry] = []
        for server_def in raw.get("servers", []):
            overrides: dict[str, McpToolOverride] = {}
            for tool_name, override_data in server_def.get("tool_overrides", {}).items():
                overrides[tool_name] = McpToolOverride(
                    triggers=override_data.get("triggers", []),
                    keywords=override_data.get("keywords", []),
                    permission_tier=override_data.get("permission_tier"),
                )
            entry = McpServerEntry(
                name=server_def["name"],
                url=server_def.get("url", ""),
                transport=server_def.get("transport", "streamable_http"),
                timeout_seconds=server_def.get("timeout_seconds", self._connect_timeout),
                tool_prefix=server_def.get("tool_prefix", ""),
                default_permission_tier=server_def.get(
                    "default_permission_tier",
                    self._default_permission_tier,
                ),
                enabled=server_def.get("enabled", True),
                tool_overrides=overrides,
            )
            entries.append(entry)
            self._servers[entry.name] = entry
            logger.debug("Loaded MCP server: %s (%s)", entry.name, entry.url)

        return entries

    async def connect(self, server_name: str) -> bool:
        """Connect to a specific MCP server."""
        entry = self._servers.get(server_name)
        if entry is None:
            logger.error("Unknown MCP server: %s", server_name)
            return False

        if not entry.enabled:
            logger.info("MCP server %s is disabled", server_name)
            return False

        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            read_stream, write_stream, _ = await streamablehttp_client(
                entry.url,
                timeout=entry.timeout_seconds,
            ).__aenter__()
            session = ClientSession(read_stream, write_stream)
            await session.__aenter__()
            await session.initialize()
            self._sessions[server_name] = session
            self._connected.add(server_name)
            logger.info("Connected to MCP server: %s", server_name)
            return True
        except Exception:
            logger.exception("Failed to connect to MCP server: %s", server_name)
            return False

    async def connect_all(self) -> dict[str, bool]:
        """Connect to all enabled servers. Returns {name: success}."""
        results: dict[str, bool] = {}
        for name, entry in self._servers.items():
            if entry.enabled:
                results[name] = await self.connect(name)
        return results

    async def disconnect(self, server_name: str) -> None:
        """Disconnect from a specific MCP server."""
        session = self._sessions.pop(server_name, None)
        if session is not None:
            try:
                await session.__aexit__(None, None, None)
            except Exception:
                logger.exception("Error disconnecting MCP server: %s", server_name)
        self._connected.discard(server_name)

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        for name in list(self._connected):
            await self.disconnect(name)

    async def discover_tools(self, server_name: str) -> list[McpToolWrapper]:
        """Discover tools from a connected MCP server.

        Returns a list of McpToolWrapper instances ready for registration.
        """
        session = self._sessions.get(server_name)
        if session is None:
            logger.warning("Cannot discover tools — %s not connected", server_name)
            return []

        entry = self._servers[server_name]

        try:
            result = await session.list_tools()
            wrappers: list[McpToolWrapper] = []

            for tool in result.tools:
                prefixed = f"{entry.tool_prefix}__{tool.name}"

                # Determine permission tier
                override = entry.tool_overrides.get(tool.name)
                tier = entry.default_permission_tier
                if override and override.permission_tier is not None:
                    tier = override.permission_tier

                info = McpToolInfo(
                    server_name=server_name,
                    original_name=tool.name,
                    prefixed_name=prefixed,
                    description=tool.description or "",
                    permission_tier=tier,
                    input_schema=tool.inputSchema if tool.inputSchema else {},
                )
                wrapper = McpToolWrapper(info=info, call_fn=self.call_tool)
                wrappers.append(wrapper)
                logger.debug("Discovered MCP tool: %s → %s", tool.name, prefixed)

            return wrappers
        except Exception:
            logger.exception("Failed to discover tools from %s", server_name)
            return []

    async def discover_all_tools(self) -> list[McpToolWrapper]:
        """Discover tools from all connected servers."""
        all_wrappers: list[McpToolWrapper] = []
        for name in self._connected:
            wrappers = await self.discover_tools(name)
            all_wrappers.extend(wrappers)
        return all_wrappers

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Call a tool on a specific MCP server."""
        session = self._sessions.get(server_name)
        if session is None:
            msg = f"MCP server {server_name} not connected"
            raise ConnectionError(msg)

        result = await session.call_tool(tool_name, arguments)

        # Extract text content from MCP result
        texts: list[str] = []
        for content in result.content:
            if hasattr(content, "text"):
                texts.append(content.text)

        return {
            "text": "\n".join(texts) if texts else "",
            "is_error": result.isError or False,
            "content_count": len(result.content),
        }

    async def health_check(self, server_name: str) -> bool:
        """Check if a server connection is healthy via ping."""
        session = self._sessions.get(server_name)
        if session is None:
            return False
        try:
            await session.send_ping()
            return True
        except Exception:
            return False

    async def health_check_all(self) -> dict[str, bool]:
        """Health check all connected servers."""
        results: dict[str, bool] = {}
        for name in self._connected:
            results[name] = await self.health_check(name)
        return results
