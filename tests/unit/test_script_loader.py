"""Tests for script-based tool loader (DD-050)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex.agent.tools.script_loader import load_script_tool

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tool_dir(tmp_path: Path) -> Path:
    """Create a valid script tool directory."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()

    manifest = {
        "name": "test-tool",
        "description": "A test tool",
        "version": 1,
        "permission_tier": 0,
        "triggers": [r"test\s+(\w+)"],
        "keywords": ["test", "example"],
        "parameters": {
            "input": {"type": "string", "required": True, "description": "Test input"},
        },
        "entry_point": "scripts/run.py",
        "timeout_seconds": 5,
    }
    import yaml

    (tmp_path / "TOOL.yaml").write_text(yaml.dump(manifest))

    # Create a working script
    (scripts_dir / "run.py").write_text(
        "import json, sys\n"
        "data = json.loads(sys.stdin.read())\n"
        'result = {"display_text": f"Result: {data.get(\'input\', \'none\')}", "data": data}\n'
        "json.dump(result, sys.stdout)\n"
    )

    return tmp_path


@pytest.fixture
def failing_tool_dir(tmp_path: Path) -> Path:
    """Create a script tool that exits with error."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()

    manifest = {"name": "failing-tool", "entry_point": "scripts/run.py", "timeout_seconds": 5}
    import yaml

    (tmp_path / "TOOL.yaml").write_text(yaml.dump(manifest))
    (scripts_dir / "run.py").write_text(
        'import sys\nprint("something went wrong", file=sys.stderr)\nsys.exit(1)\n'
    )

    return tmp_path


# ---------------------------------------------------------------------------
# Loading tests
# ---------------------------------------------------------------------------


class TestScriptToolLoading:
    """Tests for loading script tools from TOOL.yaml."""

    def test_load_valid_tool(self, tool_dir: Path) -> None:
        tool = load_script_tool(tool_dir)
        assert tool is not None
        assert tool.name == "test-tool"

    def test_load_missing_manifest(self, tmp_path: Path) -> None:
        tool = load_script_tool(tmp_path)
        assert tool is None

    def test_load_invalid_manifest(self, tmp_path: Path) -> None:
        (tmp_path / "TOOL.yaml").write_text("just a string")
        tool = load_script_tool(tmp_path)
        assert tool is None

    def test_load_manifest_missing_name(self, tmp_path: Path) -> None:
        (tmp_path / "TOOL.yaml").write_text("description: no name field")
        tool = load_script_tool(tmp_path)
        assert tool is None


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


class TestScriptToolProperties:
    """Tests for ScriptTool properties."""

    def test_name(self, tool_dir: Path) -> None:
        tool = load_script_tool(tool_dir)
        assert tool is not None
        assert tool.name == "test-tool"

    def test_description(self, tool_dir: Path) -> None:
        tool = load_script_tool(tool_dir)
        assert tool is not None
        assert tool.description == "A test tool"

    def test_permission_tier(self, tool_dir: Path) -> None:
        tool = load_script_tool(tool_dir)
        assert tool is not None
        assert tool.permission_tier == 0

    def test_triggers(self, tool_dir: Path) -> None:
        tool = load_script_tool(tool_dir)
        assert tool is not None
        assert len(tool.triggers) == 1

    def test_keywords(self, tool_dir: Path) -> None:
        tool = load_script_tool(tool_dir)
        assert tool is not None
        assert "test" in tool.keywords

    def test_enabled_default(self, tool_dir: Path) -> None:
        tool = load_script_tool(tool_dir)
        assert tool is not None
        assert tool.enabled is True

    def test_enable_disable(self, tool_dir: Path) -> None:
        tool = load_script_tool(tool_dir)
        assert tool is not None
        tool.enabled = False
        assert tool.enabled is False

    def test_get_schema(self, tool_dir: Path) -> None:
        tool = load_script_tool(tool_dir)
        assert tool is not None
        schema = tool.get_schema()
        assert schema["name"] == "test-tool"
        assert "parameters" in schema
        assert "input" in schema["parameters"]["properties"]


# ---------------------------------------------------------------------------
# Execution tests
# ---------------------------------------------------------------------------


class TestScriptToolExecution:
    """Tests for script tool execution."""

    async def test_execute_success(self, tool_dir: Path) -> None:
        tool = load_script_tool(tool_dir)
        assert tool is not None
        result = await tool.execute({"input": "hello"})
        assert result.success is True
        assert result.display_text == "Result: hello"
        assert result.data == {"input": "hello"}

    async def test_execute_failure(self, failing_tool_dir: Path) -> None:
        tool = load_script_tool(failing_tool_dir)
        assert tool is not None
        result = await tool.execute({})
        assert result.success is False
        assert "something went wrong" in (result.error or "")

    async def test_execute_disabled_tool(self, tool_dir: Path) -> None:
        tool = load_script_tool(tool_dir)
        assert tool is not None
        tool.enabled = False
        result = await tool.execute({"input": "test"})
        assert result.success is False
        assert "disabled" in (result.error or "")

    async def test_execute_missing_entry_point(self, tmp_path: Path) -> None:
        import yaml

        manifest = {"name": "no-script", "entry_point": "scripts/missing.py"}
        (tmp_path / "TOOL.yaml").write_text(yaml.dump(manifest))

        tool = load_script_tool(tmp_path)
        assert tool is not None
        result = await tool.execute({})
        assert result.success is False
        assert "not found" in (result.error or "")

    async def test_execute_timeout(self, tmp_path: Path) -> None:
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        import yaml

        manifest = {"name": "slow-tool", "entry_point": "scripts/run.py", "timeout_seconds": 0.1}
        (tmp_path / "TOOL.yaml").write_text(yaml.dump(manifest))
        (scripts_dir / "run.py").write_text("import time; time.sleep(10)\n")

        tool = load_script_tool(tmp_path)
        assert tool is not None
        result = await tool.execute({})
        assert result.success is False
        assert "timed out" in (result.error or "")
