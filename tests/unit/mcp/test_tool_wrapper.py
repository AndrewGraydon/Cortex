"""Tests for MCP tool wrapper — adapts MCP tools to Cortex Tool protocol."""

from __future__ import annotations

from typing import Any

from cortex.agent.protocols import Tool
from cortex.mcp.tool_wrapper import McpToolWrapper
from cortex.mcp.types import McpToolInfo


def _make_info(
    server_name: str = "test_server",
    original_name: str = "get_status",
    prefixed_name: str = "test__get_status",
    description: str = "Get system status",
    permission_tier: int = 2,
    input_schema: dict[str, Any] | None = None,
) -> McpToolInfo:
    return McpToolInfo(
        server_name=server_name,
        original_name=original_name,
        prefixed_name=prefixed_name,
        description=description,
        permission_tier=permission_tier,
        input_schema=input_schema or {"type": "object", "properties": {}},
    )


class TestToolWrapperProtocol:
    def test_satisfies_tool_protocol(self) -> None:
        wrapper = McpToolWrapper(info=_make_info())
        assert isinstance(wrapper, Tool)

    def test_name(self) -> None:
        wrapper = McpToolWrapper(info=_make_info(prefixed_name="ha__lights"))
        assert wrapper.name == "ha__lights"

    def test_description(self) -> None:
        wrapper = McpToolWrapper(info=_make_info(description="Toggle lights"))
        assert wrapper.description == "Toggle lights"

    def test_permission_tier(self) -> None:
        wrapper = McpToolWrapper(info=_make_info(permission_tier=1))
        assert wrapper.permission_tier == 1

    def test_server_name(self) -> None:
        wrapper = McpToolWrapper(info=_make_info(server_name="homeassistant"))
        assert wrapper.server_name == "homeassistant"

    def test_original_name(self) -> None:
        wrapper = McpToolWrapper(info=_make_info(original_name="get_lights"))
        assert wrapper.original_name == "get_lights"


class TestToolWrapperSchema:
    def test_schema_name(self) -> None:
        wrapper = McpToolWrapper(info=_make_info(prefixed_name="ha__lights"))
        schema = wrapper.get_schema()
        assert schema["name"] == "ha__lights"

    def test_schema_description(self) -> None:
        wrapper = McpToolWrapper(info=_make_info(description="Control lights"))
        schema = wrapper.get_schema()
        assert schema["description"] == "Control lights"

    def test_schema_parameters(self) -> None:
        params = {
            "type": "object",
            "properties": {
                "room": {"type": "string", "description": "Room name"},
            },
            "required": ["room"],
        }
        wrapper = McpToolWrapper(info=_make_info(input_schema=params))
        schema = wrapper.get_schema()
        assert schema["parameters"] == params

    def test_schema_default_parameters(self) -> None:
        """Default input_schema should be an empty dict."""
        info = McpToolInfo(
            server_name="test",
            original_name="tool",
            prefixed_name="test__tool",
            description="desc",
            permission_tier=0,
        )
        wrapper = McpToolWrapper(info=info)
        schema = wrapper.get_schema()
        assert schema["parameters"] == {}


class TestToolWrapperExecute:
    async def test_no_call_fn(self) -> None:
        wrapper = McpToolWrapper(info=_make_info(), call_fn=None)
        result = await wrapper.execute({"key": "value"})
        assert result.success is False
        assert "not connected" in result.error.lower()

    async def test_successful_call(self) -> None:
        async def mock_call(server: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
            return {"text": "Status: OK", "is_error": False}

        wrapper = McpToolWrapper(info=_make_info(), call_fn=mock_call)
        result = await wrapper.execute({"check": True})
        assert result.success is True
        assert "Status: OK" in result.display_text

    async def test_call_passes_correct_args(self) -> None:
        captured: dict[str, Any] = {}

        async def mock_call(server: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
            captured["server"] = server
            captured["tool"] = tool
            captured["args"] = args
            return {"text": "done"}

        info = _make_info(server_name="ha", original_name="toggle_light")
        wrapper = McpToolWrapper(info=info, call_fn=mock_call)
        await wrapper.execute({"room": "kitchen"})

        assert captured["server"] == "ha"
        assert captured["tool"] == "toggle_light"
        assert captured["args"] == {"room": "kitchen"}

    async def test_call_error_returns_failure(self) -> None:
        async def failing_call(server: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
            msg = "Connection refused"
            raise ConnectionError(msg)

        wrapper = McpToolWrapper(info=_make_info(), call_fn=failing_call)
        result = await wrapper.execute({})
        assert result.success is False
        assert "Connection refused" in result.error

    async def test_display_text_truncated(self) -> None:
        async def mock_call(server: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
            return {"text": "A" * 200}

        wrapper = McpToolWrapper(info=_make_info(), call_fn=mock_call)
        result = await wrapper.execute({})
        assert result.success is True
        assert len(result.display_text) <= 100

    async def test_non_dict_result(self) -> None:
        async def mock_call(server: str, tool: str, args: dict[str, Any]) -> str:
            return "plain text result"  # type: ignore[return-value]

        wrapper = McpToolWrapper(info=_make_info(), call_fn=mock_call)
        result = await wrapper.execute({})
        assert result.success is True
