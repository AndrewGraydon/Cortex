"""Tests for tool manager web UI (Milestone 3a.6)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from cortex.agent.tools.registry import ToolRegistry
from cortex.config import CortexConfig
from cortex.web.app import create_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockTool:
    """Minimal tool for testing the web API."""

    def __init__(self, name: str, description: str = "", tier: int = 0) -> None:
        self.name = name
        self.description = description
        self.permission_tier = tier

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": {}},
        }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        pass


def _make_app(**overrides: object) -> TestClient:
    app = create_app(config=CortexConfig(), enable_auth=False, **overrides)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tool page rendering tests
# ---------------------------------------------------------------------------


class TestToolsPage:
    """Tests for GET /tools page."""

    def test_page_returns_200(self) -> None:
        with _make_app() as client:
            response = client.get("/tools")
            assert response.status_code == 200

    def test_page_has_title(self) -> None:
        with _make_app() as client:
            response = client.get("/tools")
            assert "Tools" in response.text

    def test_page_has_reload_button(self) -> None:
        with _make_app() as client:
            response = client.get("/tools")
            assert "Reload" in response.text

    def test_page_has_search_input(self) -> None:
        with _make_app() as client:
            response = client.get("/tools")
            assert "tool-search" in response.text

    def test_page_has_tools_list_container(self) -> None:
        with _make_app() as client:
            response = client.get("/tools")
            assert "tools-list" in response.text


# ---------------------------------------------------------------------------
# Tool API tests
# ---------------------------------------------------------------------------


class TestToolsAPI:
    """Tests for GET /api/tools."""

    def test_returns_200(self) -> None:
        with _make_app() as client:
            response = client.get("/api/tools")
            assert response.status_code == 200

    def test_empty_without_registry(self) -> None:
        with _make_app() as client:
            data = client.get("/api/tools").json()
            assert data["tools"] == []

    def test_lists_registered_tools(self) -> None:
        registry = ToolRegistry()
        registry.register(_MockTool("time", "Get time", tier=0))
        registry.register(_MockTool("weather", "Get weather", tier=1))
        with _make_app(tool_registry=registry) as client:
            data = client.get("/api/tools").json()
            assert len(data["tools"]) == 2

    def test_tool_info_fields(self) -> None:
        registry = ToolRegistry()
        registry.register(_MockTool("time", "Get time", tier=0))
        with _make_app(tool_registry=registry) as client:
            tools = client.get("/api/tools").json()["tools"]
            tool = tools[0]
            assert tool["name"] == "time"
            assert tool["description"] == "Get time"
            assert tool["tier"] == 0
            assert tool["type"] == "python"
            assert tool["enabled"] is True

    def test_script_tool_metadata(self) -> None:
        """Script tools should include type, triggers, and keywords."""
        import tempfile
        from pathlib import Path

        import yaml

        from cortex.agent.tools.script_loader import load_script_tool

        with tempfile.TemporaryDirectory() as td:
            tool_dir = Path(td)
            (tool_dir / "scripts").mkdir()
            (tool_dir / "TOOL.yaml").write_text(
                yaml.dump({
                    "name": "test-script",
                    "description": "A script tool",
                    "permission_tier": 0,
                    "triggers": [r"test\s+(\w+)"],
                    "keywords": ["test"],
                    "entry_point": "scripts/run.py",
                })
            )
            run_code = 'import json,sys; json.dump({}, sys.stdout)\n'
            (tool_dir / "scripts" / "run.py").write_text(run_code)

            tool = load_script_tool(tool_dir)
            assert tool is not None

            registry = ToolRegistry()
            registry.register(tool)

            with _make_app(tool_registry=registry) as client:
                tools = client.get("/api/tools").json()["tools"]
                assert len(tools) == 1
                t = tools[0]
                assert t["type"] == "script"
                assert t["triggers"] == [r"test\s+(\w+)"]
                assert "test" in t["keywords"]


# ---------------------------------------------------------------------------
# Tool reload API tests
# ---------------------------------------------------------------------------


class TestToolReload:
    """Tests for POST /api/tools/reload."""

    def test_reload_without_registry(self) -> None:
        with _make_app() as client:
            response = client.post("/api/tools/reload")
            assert response.status_code == 200
            assert response.json()["reloaded"] == 0

    def test_reload_discovers_tools(self) -> None:
        """Reload should discover tools from the tools directory."""
        import tempfile
        from pathlib import Path

        import yaml

        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            tool_subdir = tools_dir / "hello"
            tool_subdir.mkdir()
            (tool_subdir / "scripts").mkdir()
            (tool_subdir / "TOOL.yaml").write_text(
                yaml.dump({"name": "hello", "entry_point": "scripts/run.py"})
            )
            run_code = 'import json,sys; json.dump({}, sys.stdout)\n'
            (tool_subdir / "scripts" / "run.py").write_text(run_code)

            registry = ToolRegistry()
            with _make_app(tool_registry=registry, tools_dir=tools_dir) as client:
                response = client.post("/api/tools/reload")
                data = response.json()
                assert data["reloaded"] == 1
                assert data["total"] == 1
