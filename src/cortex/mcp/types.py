"""MCP types — server entry definitions and tool metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class McpToolOverride:
    """Per-tool overrides for MCP-discovered tools."""

    triggers: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    permission_tier: int | None = None


@dataclass
class McpServerEntry:
    """Definition of an external MCP server to connect to."""

    name: str
    url: str
    transport: str = "streamable_http"  # "streamable_http" or "stdio"
    timeout_seconds: int = 5
    tool_prefix: str = ""  # If empty, defaults to server name
    default_permission_tier: int = 2
    enabled: bool = True
    tool_overrides: dict[str, McpToolOverride] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.tool_prefix:
            self.tool_prefix = self.name


@dataclass
class McpToolInfo:
    """Metadata about an MCP-discovered tool."""

    server_name: str
    original_name: str
    prefixed_name: str
    description: str
    permission_tier: int
    input_schema: dict[str, Any] = field(default_factory=dict)
