"""Tests for script tool discovery (DD-050)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cortex.agent.tools.discovery import discover_script_tools

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tools_dir(tmp_path: Path) -> Path:
    """Create a tools directory with two valid script tools."""
    # Tool 1: greeting
    greeting_dir = tmp_path / "greeting"
    greeting_dir.mkdir()
    (greeting_dir / "scripts").mkdir()
    (greeting_dir / "TOOL.yaml").write_text(
        yaml.dump({
            "name": "greeting",
            "description": "Say hello",
            "permission_tier": 0,
            "entry_point": "scripts/run.py",
        })
    )
    (greeting_dir / "scripts" / "run.py").write_text(
        'import json, sys\n'
        'data = json.loads(sys.stdin.read())\n'
        'json.dump({"display_text": "Hello!"}, sys.stdout)\n'
    )

    # Tool 2: timer
    timer_dir = tmp_path / "timer"
    timer_dir.mkdir()
    (timer_dir / "scripts").mkdir()
    (timer_dir / "TOOL.yaml").write_text(
        yaml.dump({
            "name": "timer",
            "description": "Set a timer",
            "permission_tier": 1,
            "entry_point": "scripts/run.py",
        })
    )
    (timer_dir / "scripts" / "run.py").write_text(
        'import json, sys\n'
        'json.dump({"display_text": "Timer set"}, sys.stdout)\n'
    )

    return tmp_path


# ---------------------------------------------------------------------------
# Discovery tests
# ---------------------------------------------------------------------------


class TestDiscoverScriptTools:
    """Tests for discover_script_tools()."""

    def test_discovers_valid_tools(self, tools_dir: Path) -> None:
        tools = discover_script_tools(tools_dir)
        assert len(tools) == 2

    def test_tool_names(self, tools_dir: Path) -> None:
        tools = discover_script_tools(tools_dir)
        names = {t.name for t in tools}
        assert names == {"greeting", "timer"}

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        tools = discover_script_tools(tmp_path / "nonexistent")
        assert tools == []

    def test_empty_directory(self, tmp_path: Path) -> None:
        tools = discover_script_tools(tmp_path)
        assert tools == []

    def test_skips_hidden_directories(self, tools_dir: Path) -> None:
        hidden = tools_dir / ".hidden-tool"
        hidden.mkdir()
        (hidden / "TOOL.yaml").write_text(yaml.dump({"name": "hidden"}))
        tools = discover_script_tools(tools_dir)
        names = {t.name for t in tools}
        assert "hidden" not in names

    def test_skips_underscore_directories(self, tools_dir: Path) -> None:
        internal = tools_dir / "_internal"
        internal.mkdir()
        (internal / "TOOL.yaml").write_text(yaml.dump({"name": "internal"}))
        tools = discover_script_tools(tools_dir)
        names = {t.name for t in tools}
        assert "internal" not in names

    def test_skips_files_not_dirs(self, tools_dir: Path) -> None:
        (tools_dir / "README.md").write_text("Not a tool directory")
        tools = discover_script_tools(tools_dir)
        assert len(tools) == 2  # Only the two valid tool dirs

    def test_skips_invalid_manifests(self, tools_dir: Path) -> None:
        broken = tools_dir / "broken"
        broken.mkdir()
        (broken / "TOOL.yaml").write_text("just a string")
        tools = discover_script_tools(tools_dir)
        assert len(tools) == 2  # Broken tool skipped

    def test_skips_dirs_without_manifest(self, tools_dir: Path) -> None:
        no_manifest = tools_dir / "empty-dir"
        no_manifest.mkdir()
        tools = discover_script_tools(tools_dir)
        assert len(tools) == 2

    def test_sorted_by_directory_name(self, tools_dir: Path) -> None:
        tools = discover_script_tools(tools_dir)
        dirs = [t.tool_dir.name for t in tools]
        assert dirs == sorted(dirs)

    def test_tool_permission_tiers(self, tools_dir: Path) -> None:
        tools = discover_script_tools(tools_dir)
        tiers = {t.name: t.permission_tier for t in tools}
        assert tiers["greeting"] == 0
        assert tiers["timer"] == 1


# ---------------------------------------------------------------------------
# Integration with ToolRegistry
# ---------------------------------------------------------------------------


class TestDiscoveryRegistration:
    """Tests that discovered tools integrate with ToolRegistry."""

    def test_register_discovered_tools(self, tools_dir: Path) -> None:
        from cortex.agent.tools.registry import ToolRegistry

        registry = ToolRegistry()
        tools = discover_script_tools(tools_dir)
        for tool in tools:
            registry.register(tool)

        assert len(registry) == 2
        assert "greeting" in registry.tool_names
        assert "timer" in registry.tool_names

    def test_get_schemas_for_discovered(self, tools_dir: Path) -> None:
        from cortex.agent.tools.registry import ToolRegistry

        registry = ToolRegistry()
        for tool in discover_script_tools(tools_dir):
            registry.register(tool)

        schemas = registry.get_schemas()
        assert len(schemas) == 2
        names = {s.name for s in schemas}
        assert names == {"greeting", "timer"}

    async def test_execute_discovered_tool(self, tools_dir: Path) -> None:
        from cortex.agent.tools.registry import ToolRegistry
        from cortex.agent.types import ToolCall

        registry = ToolRegistry()
        for tool in discover_script_tools(tools_dir):
            registry.register(tool)

        result = await registry.execute(ToolCall(name="greeting", arguments={"name": "world"}))
        assert result.success is True
        assert result.display_text == "Hello!"
