"""Agent types — definitions for dynamic agent creation."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentDefinition:
    """Definition for a dynamically created agent.

    Loaded from YAML definitions or created programmatically.
    """

    name: str
    description: str
    system_prompt: str = ""
    tools: list[str] = field(default_factory=list)
    permission_tier: int = 2
    model: str = "default"
    max_iterations: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class SuperAgent:
    """A running agent instance with state."""

    definition: AgentDefinition
    active: bool = True
    invocations: int = 0
    last_invoked_at: float = 0.0
