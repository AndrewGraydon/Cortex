"""Agent framework data types — tools, actions, routing, responses."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class IntentType(enum.Enum):
    """How an intent should be handled."""

    UTILITY = "utility"  # Direct handler, no LLM
    LLM = "llm"  # Requires LLM inference
    FAREWELL = "farewell"  # End session


@dataclass(frozen=True)
class IntentMatch:
    """Result of regex/keyword intent matching."""

    intent_id: str
    intent_type: IntentType
    tool_hint: str | None = None  # Which tool is likely needed
    extracted: dict[str, str] = field(default_factory=dict)  # Regex captures


@dataclass(frozen=True)
class RoutingDecision:
    """How an utterance should be processed."""

    intent_type: IntentType
    intent_match: IntentMatch | None = None  # None if LLM fallback
    tool_hints: list[str] = field(default_factory=list)  # Tools to inject in prompt


@dataclass(frozen=True)
class ToolCall:
    """A tool invocation parsed from LLM output."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""  # Original LLM text for debugging


@dataclass
class ToolResult:
    """Result of executing a tool."""

    tool_name: str
    success: bool
    data: Any = None  # Tool-specific result
    error: str | None = None
    display_text: str = ""  # Human-readable result for TTS


@dataclass(frozen=True)
class ActionRequest:
    """Request to execute an action through the action engine."""

    action_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    source: str = "voice"  # voice, scheduled, agent


@dataclass
class ActionResult:
    """Result of action execution."""

    action_id: str
    success: bool
    data: Any = None
    error: str | None = None
    display_text: str = ""


@dataclass
class AgentResponse:
    """Response from the agent processor to the voice pipeline."""

    text: str  # Text to speak via TTS
    tool_calls: list[ToolCall] = field(default_factory=list)  # Tools that were called
    tool_results: list[ToolResult] = field(default_factory=list)  # Results
    used_llm: bool = False  # Whether LLM was invoked
    intent_id: str | None = None  # Matched intent, if any
    llm_messages: list[dict[str, str]] | None = None  # Pre-built OpenAI messages for VLM
