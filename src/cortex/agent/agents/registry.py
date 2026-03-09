"""Agent registry — tracks built-in and dynamic agents."""

from __future__ import annotations

import logging
from typing import Any

from cortex.agent.agents.types import AgentDefinition, SuperAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Registry for managing agent definitions and instances.

    Tracks both built-in agents (registered at startup) and dynamically
    created agents (via factory + YAML definitions).
    """

    def __init__(self) -> None:
        self._definitions: dict[str, AgentDefinition] = {}
        self._instances: dict[str, SuperAgent] = {}
        self._sources: dict[str, str] = {}  # name → "builtin" | "dynamic"

    def register(
        self,
        definition: AgentDefinition,
        source: str = "dynamic",
    ) -> None:
        """Register an agent definition."""
        self._definitions[definition.name] = definition
        self._sources[definition.name] = source
        logger.info("Registered agent '%s' (source: %s)", definition.name, source)

    def unregister(self, name: str) -> bool:
        """Unregister an agent."""
        if name not in self._definitions:
            return False
        del self._definitions[name]
        self._instances.pop(name, None)
        self._sources.pop(name, None)
        return True

    def get_definition(self, name: str) -> AgentDefinition | None:
        """Get an agent definition by name."""
        return self._definitions.get(name)

    def get_instance(self, name: str) -> SuperAgent | None:
        """Get or create an agent instance."""
        if name not in self._definitions:
            return None

        if name not in self._instances:
            from cortex.agent.agents.factory import instantiate_agent

            self._instances[name] = instantiate_agent(self._definitions[name])

        return self._instances[name]

    def list_agents(self, source: str | None = None) -> list[dict[str, Any]]:
        """List all registered agents."""
        agents: list[dict[str, Any]] = []
        for name, defn in sorted(self._definitions.items()):
            agent_source = self._sources.get(name, "unknown")
            if source is not None and agent_source != source:
                continue
            instance = self._instances.get(name)
            agents.append(
                {
                    "name": name,
                    "description": defn.description,
                    "source": agent_source,
                    "tools": defn.tools,
                    "active": instance.active if instance else False,
                    "invocations": instance.invocations if instance else 0,
                }
            )
        return agents

    @property
    def agent_names(self) -> list[str]:
        """List all registered agent names."""
        return sorted(self._definitions.keys())

    def __len__(self) -> int:
        return len(self._definitions)
