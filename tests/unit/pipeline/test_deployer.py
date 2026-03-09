"""Tests for tool deployer."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cortex.agent.tools.pipeline.deployer import ToolDeployer
from cortex.agent.tools.pipeline.types import PipelineStage, ReviewResult, ToolDraft, ToolSpec


def _make_approved_draft(name: str = "test-tool") -> ToolDraft:
    """Create an approved draft ready for deployment."""
    spec = ToolSpec(name=name, description="A test tool")
    manifest = {"name": name, "description": "A test tool", "entry_point": "scripts/run.py"}
    script = (
        "import json\nimport sys\n\ndata = json.loads(sys.stdin.read())\n"
        'json.dump({"display_text": "ok", "data": data}, sys.stdout)\n'
    )
    return ToolDraft(
        spec=spec,
        manifest_yaml=yaml.dump(manifest),
        script_code=script,
        stage=PipelineStage.APPROVED,
        review_result=ReviewResult(passed=True),
    )


class TestDeploy:
    def test_deploy_creates_directory(self, tmp_path: Path) -> None:
        deployer = ToolDeployer(user_tools_dir=tmp_path / "user-tools")
        draft = _make_approved_draft()
        tool_dir = deployer.deploy(draft)
        assert tool_dir.exists()
        assert tool_dir.is_dir()

    def test_deploy_creates_manifest(self, tmp_path: Path) -> None:
        deployer = ToolDeployer(user_tools_dir=tmp_path / "user-tools")
        draft = _make_approved_draft()
        tool_dir = deployer.deploy(draft)
        assert (tool_dir / "TOOL.yaml").exists()

    def test_deploy_creates_script(self, tmp_path: Path) -> None:
        deployer = ToolDeployer(user_tools_dir=tmp_path / "user-tools")
        draft = _make_approved_draft()
        tool_dir = deployer.deploy(draft)
        assert (tool_dir / "scripts" / "run.py").exists()

    def test_deploy_manifest_content(self, tmp_path: Path) -> None:
        deployer = ToolDeployer(user_tools_dir=tmp_path / "user-tools")
        draft = _make_approved_draft()
        tool_dir = deployer.deploy(draft)
        manifest = yaml.safe_load((tool_dir / "TOOL.yaml").read_text())
        assert manifest["name"] == "test-tool"

    def test_deploy_updates_stage(self, tmp_path: Path) -> None:
        deployer = ToolDeployer(user_tools_dir=tmp_path / "user-tools")
        draft = _make_approved_draft()
        deployer.deploy(draft)
        assert draft.stage == PipelineStage.DEPLOYED

    def test_deploy_rejects_unapproved(self, tmp_path: Path) -> None:
        deployer = ToolDeployer(user_tools_dir=tmp_path / "user-tools")
        spec = ToolSpec(name="test-tool", description="Test")
        draft = ToolDraft(spec=spec, stage=PipelineStage.DRAFT)
        with pytest.raises(ValueError, match="approved"):
            deployer.deploy(draft)

    def test_deploy_rejects_duplicate(self, tmp_path: Path) -> None:
        deployer = ToolDeployer(user_tools_dir=tmp_path / "user-tools")
        draft1 = _make_approved_draft()
        deployer.deploy(draft1)
        draft2 = _make_approved_draft()
        with pytest.raises(ValueError, match="already exists"):
            deployer.deploy(draft2)

    def test_deploy_rejects_over_limit(self, tmp_path: Path) -> None:
        deployer = ToolDeployer(user_tools_dir=tmp_path / "user-tools", max_tools=1)
        draft1 = _make_approved_draft(name="tool-one")
        deployer.deploy(draft1)
        draft2 = _make_approved_draft(name="tool-two")
        with pytest.raises(ValueError, match="limit"):
            deployer.deploy(draft2)

    def test_deploy_returns_correct_path(self, tmp_path: Path) -> None:
        deployer = ToolDeployer(user_tools_dir=tmp_path / "user-tools")
        draft = _make_approved_draft(name="my-tool")
        tool_dir = deployer.deploy(draft)
        assert tool_dir.name == "my-tool"


class TestRemove:
    def test_remove_deployed(self, tmp_path: Path) -> None:
        deployer = ToolDeployer(user_tools_dir=tmp_path / "user-tools")
        draft = _make_approved_draft()
        deployer.deploy(draft)
        assert deployer.remove("test-tool") is True
        assert not (tmp_path / "user-tools" / "test-tool").exists()

    def test_remove_nonexistent(self, tmp_path: Path) -> None:
        deployer = ToolDeployer(user_tools_dir=tmp_path / "user-tools")
        assert deployer.remove("nonexistent") is False


class TestListDeployed:
    def test_empty_directory(self, tmp_path: Path) -> None:
        deployer = ToolDeployer(user_tools_dir=tmp_path / "user-tools")
        assert deployer.list_deployed() == []

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        deployer = ToolDeployer(user_tools_dir=tmp_path / "nonexistent")
        assert deployer.list_deployed() == []

    def test_lists_deployed_tools(self, tmp_path: Path) -> None:
        deployer = ToolDeployer(user_tools_dir=tmp_path / "user-tools")
        draft = _make_approved_draft()
        deployer.deploy(draft)
        tools = deployer.list_deployed()
        assert len(tools) == 1
        assert tools[0]["name"] == "test-tool"

    def test_lists_multiple_tools(self, tmp_path: Path) -> None:
        deployer = ToolDeployer(user_tools_dir=tmp_path / "user-tools")
        for name in ["tool-alpha", "tool-beta"]:
            draft = _make_approved_draft(name=name)
            deployer.deploy(draft)
        tools = deployer.list_deployed()
        assert len(tools) == 2
        names = {t["name"] for t in tools}
        assert "tool-alpha" in names
        assert "tool-beta" in names
