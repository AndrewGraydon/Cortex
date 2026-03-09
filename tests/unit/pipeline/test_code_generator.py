"""Tests for tool code generator."""

from __future__ import annotations

import yaml

from cortex.agent.tools.pipeline.code_generator import generate_code
from cortex.agent.tools.pipeline.types import PipelineStage, ToolSpec


class TestGenerateCode:
    def test_produces_draft(self) -> None:
        spec = ToolSpec(name="my-tool", description="A test tool")
        draft = generate_code(spec)
        assert draft.stage == PipelineStage.DRAFT
        assert draft.spec is spec

    def test_manifest_yaml_valid(self) -> None:
        spec = ToolSpec(name="my-tool", description="A test tool")
        draft = generate_code(spec)
        manifest = yaml.safe_load(draft.manifest_yaml)
        assert isinstance(manifest, dict)
        assert manifest["name"] == "my-tool"

    def test_manifest_has_required_fields(self) -> None:
        spec = ToolSpec(name="my-tool", description="A test tool")
        draft = generate_code(spec)
        manifest = yaml.safe_load(draft.manifest_yaml)
        assert "name" in manifest
        assert "description" in manifest
        assert "version" in manifest
        assert "permission_tier" in manifest
        assert "entry_point" in manifest

    def test_manifest_entry_point(self) -> None:
        spec = ToolSpec(name="my-tool", description="A test tool")
        draft = generate_code(spec)
        manifest = yaml.safe_load(draft.manifest_yaml)
        assert manifest["entry_point"] == "scripts/run.py"

    def test_manifest_includes_keywords(self) -> None:
        spec = ToolSpec(name="my-tool", description="Test", keywords=["test", "example"])
        draft = generate_code(spec)
        manifest = yaml.safe_load(draft.manifest_yaml)
        assert manifest["keywords"] == ["test", "example"]

    def test_manifest_includes_parameters(self) -> None:
        spec = ToolSpec(
            name="my-tool",
            description="Test",
            parameters={"query": {"type": "string"}},
        )
        draft = generate_code(spec)
        manifest = yaml.safe_load(draft.manifest_yaml)
        assert "query" in manifest["parameters"]

    def test_manifest_omits_empty_keywords(self) -> None:
        spec = ToolSpec(name="my-tool", description="Test")
        draft = generate_code(spec)
        manifest = yaml.safe_load(draft.manifest_yaml)
        assert "keywords" not in manifest

    def test_script_code_is_python(self) -> None:
        spec = ToolSpec(name="my-tool", description="A test tool")
        draft = generate_code(spec)
        assert "import json" in draft.script_code
        assert "import sys" in draft.script_code
        assert "def main" in draft.script_code

    def test_script_reads_stdin(self) -> None:
        spec = ToolSpec(name="my-tool", description="A test tool")
        draft = generate_code(spec)
        assert "sys.stdin" in draft.script_code

    def test_script_writes_json(self) -> None:
        spec = ToolSpec(name="my-tool", description="A test tool")
        draft = generate_code(spec)
        assert "json.dump" in draft.script_code

    def test_script_has_main_guard(self) -> None:
        spec = ToolSpec(name="my-tool", description="A test tool")
        draft = generate_code(spec)
        assert '__name__ == "__main__"' in draft.script_code

    def test_script_extracts_parameters(self) -> None:
        spec = ToolSpec(
            name="my-tool",
            description="Test",
            parameters={"query": {"type": "string"}, "limit": {"type": "integer"}},
        )
        draft = generate_code(spec)
        assert 'data.get("query"' in draft.script_code
        assert 'data.get("limit"' in draft.script_code

    def test_draft_has_timestamps(self) -> None:
        spec = ToolSpec(name="my-tool", description="Test")
        draft = generate_code(spec)
        assert draft.created_at > 0
        assert draft.updated_at > 0
