"""Agent Card builder — constructs the A2A Agent Card from config and skills."""

from __future__ import annotations

import logging
from typing import Any

from cortex.a2a.types import A2aSkill, AgentCard

logger = logging.getLogger(__name__)

# Default skills based on Cortex super agents
DEFAULT_SKILLS: dict[str, A2aSkill] = {
    "general": A2aSkill(
        id="general",
        name="General Assistant",
        description="General-purpose conversational AI for questions, tasks, and information",
        tags=["general", "conversation", "qa"],
        examples=[
            "What is the capital of France?",
            "Explain quantum computing",
            "Help me write an email",
        ],
    ),
    "home": A2aSkill(
        id="home",
        name="Home Automation",
        description="Control smart home devices, check status, and manage automations",
        tags=["home", "iot", "automation"],
        examples=[
            "Turn on the living room lights",
            "What is the temperature inside?",
        ],
    ),
    "research": A2aSkill(
        id="research",
        name="Research Assistant",
        description="Deep research, summarization, and analysis of topics",
        tags=["research", "analysis", "summarization"],
        examples=[
            "Research the latest developments in AI",
            "Summarize this article",
        ],
    ),
    "pim": A2aSkill(
        id="pim",
        name="Personal Information Manager",
        description="Manage calendar, email, contacts, and personal data",
        tags=["calendar", "email", "contacts", "pim"],
        examples=[
            "What's on my calendar today?",
            "Check my email",
            "Schedule a meeting for tomorrow",
        ],
    ),
    "planner": A2aSkill(
        id="planner",
        name="Task Planner",
        description="Plan and organize multi-step tasks and workflows",
        tags=["planning", "workflow", "tasks"],
        examples=[
            "Plan a weekend trip to the mountains",
            "Create a project timeline",
        ],
    ),
}


class AgentCardBuilder:
    """Builds an A2A Agent Card from configuration.

    The Agent Card is served at /.well-known/agent.json per the A2A spec.
    """

    def __init__(
        self,
        name: str = "Cortex",
        description: str = "Privacy-first local AI voice assistant",
        base_url: str = "http://localhost:8000",
        version: str = "0.1.0",
    ) -> None:
        self._name = name
        self._description = description
        self._base_url = base_url.rstrip("/")
        self._version = version
        self._skills: list[A2aSkill] = []
        self._capabilities: dict[str, Any] = {
            "streaming": False,
            "pushNotifications": False,
        }
        self._authentication: dict[str, Any] = {}

    def add_skill(self, skill: A2aSkill) -> AgentCardBuilder:
        """Add a skill to the Agent Card."""
        self._skills.append(skill)
        return self

    def add_default_skills(
        self,
        skill_ids: list[str] | None = None,
    ) -> AgentCardBuilder:
        """Add default Cortex skills by ID."""
        ids = skill_ids or list(DEFAULT_SKILLS.keys())
        for skill_id in ids:
            skill = DEFAULT_SKILLS.get(skill_id)
            if skill:
                self._skills.append(skill)
        return self

    def set_capabilities(self, **kwargs: Any) -> AgentCardBuilder:
        """Set Agent Card capabilities."""
        self._capabilities.update(kwargs)
        return self

    def set_authentication(self, **kwargs: Any) -> AgentCardBuilder:
        """Set authentication requirements."""
        self._authentication.update(kwargs)
        return self

    def build(self) -> AgentCard:
        """Build the Agent Card."""
        return AgentCard(
            name=self._name,
            description=self._description,
            url=f"{self._base_url}/a2a",
            version=self._version,
            skills=list(self._skills),
            capabilities=self._capabilities,
            authentication=self._authentication,
        )
