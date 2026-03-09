"""Agent factory — creates dynamic agents from YAML definitions.

Agents are validated against a schema and registered with the AgentRegistry.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from cortex.agent.agents.types import AgentDefinition, SuperAgent

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {"name", "description"}
OPTIONAL_FIELDS = {
    "system_prompt",
    "tools",
    "permission_tier",
    "model",
    "max_iterations",
    "metadata",
}


def create_agent_from_dict(data: dict[str, Any]) -> AgentDefinition:
    """Create an AgentDefinition from a dict.

    Args:
        data: Agent definition data.

    Returns:
        Validated AgentDefinition.

    Raises:
        ValueError: If required fields are missing or invalid.
    """
    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        msg = f"Missing required fields: {', '.join(sorted(missing))}"
        raise ValueError(msg)

    name = data["name"]
    if not isinstance(name, str) or len(name) < 2:
        msg = "Agent name must be a string of at least 2 characters"
        raise ValueError(msg)

    return AgentDefinition(
        name=name,
        description=data["description"],
        system_prompt=data.get("system_prompt", ""),
        tools=data.get("tools", []),
        permission_tier=data.get("permission_tier", 2),
        model=data.get("model", "default"),
        max_iterations=data.get("max_iterations", 5),
        metadata=data.get("metadata", {}),
    )


def create_agent_from_yaml(yaml_path: Path) -> AgentDefinition:
    """Create an AgentDefinition from a YAML file.

    Args:
        yaml_path: Path to agent YAML definition.

    Returns:
        Validated AgentDefinition.

    Raises:
        ValueError: If file is invalid.
        FileNotFoundError: If file doesn't exist.
    """
    if not yaml_path.exists():
        msg = f"Agent definition not found: {yaml_path}"
        raise FileNotFoundError(msg)

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        msg = f"Agent definition must be a YAML mapping: {yaml_path}"
        raise ValueError(msg)

    return create_agent_from_dict(data)


def instantiate_agent(definition: AgentDefinition) -> SuperAgent:
    """Create a running agent instance from a definition."""
    return SuperAgent(definition=definition)
