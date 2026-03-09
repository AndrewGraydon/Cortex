"""Tests for agent factory."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cortex.agent.agents.factory import (
    create_agent_from_dict,
    create_agent_from_yaml,
    instantiate_agent,
)
from cortex.agent.agents.types import AgentDefinition


class TestCreateFromDict:
    def test_basic_agent(self) -> None:
        defn = create_agent_from_dict({"name": "test-agent", "description": "A test agent"})
        assert defn.name == "test-agent"
        assert defn.description == "A test agent"

    def test_with_tools(self) -> None:
        defn = create_agent_from_dict(
            {"name": "tool-agent", "description": "Has tools", "tools": ["clock", "calculator"]}
        )
        assert "clock" in defn.tools

    def test_with_system_prompt(self) -> None:
        defn = create_agent_from_dict(
            {
                "name": "prompt-agent",
                "description": "Has prompt",
                "system_prompt": "You are a helper.",
            }
        )
        assert defn.system_prompt == "You are a helper."

    def test_custom_tier(self) -> None:
        defn = create_agent_from_dict(
            {"name": "restricted", "description": "Restricted", "permission_tier": 3}
        )
        assert defn.permission_tier == 3

    def test_missing_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Missing required"):
            create_agent_from_dict({"description": "No name"})

    def test_missing_description_raises(self) -> None:
        with pytest.raises(ValueError, match="Missing required"):
            create_agent_from_dict({"name": "no-desc"})

    def test_short_name_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 2"):
            create_agent_from_dict({"name": "x", "description": "Too short name"})

    def test_defaults(self) -> None:
        defn = create_agent_from_dict({"name": "default-agent", "description": "Test"})
        assert defn.permission_tier == 2
        assert defn.model == "default"
        assert defn.max_iterations == 5
        assert defn.tools == []


class TestCreateFromYaml:
    def test_load_yaml(self, tmp_path: Path) -> None:
        data = {"name": "yaml-agent", "description": "From YAML", "tools": ["clock"]}
        yaml_path = tmp_path / "agent.yaml"
        yaml_path.write_text(yaml.dump(data))
        defn = create_agent_from_yaml(yaml_path)
        assert defn.name == "yaml-agent"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            create_agent_from_yaml(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "agent.yaml"
        yaml_path.write_text("just a string")
        with pytest.raises(ValueError, match="YAML mapping"):
            create_agent_from_yaml(yaml_path)


class TestInstantiateAgent:
    def test_creates_instance(self) -> None:
        defn = AgentDefinition(name="test", description="Test")
        agent = instantiate_agent(defn)
        assert agent.definition is defn
        assert agent.active is True
        assert agent.invocations == 0
