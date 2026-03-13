"""Reasoning layer data types — tool schemas, context budget, assembled prompts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolSchema:
    """Tool description in canonical (OpenAI function calling) format.

    Kept intentionally concise for the 2,047 token budget.
    """

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to OpenAI function calling format."""
        result: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
        }
        if self.parameters:
            result["parameters"] = {
                "type": "object",
                "properties": self.parameters,
            }
        return result


@dataclass(frozen=True)
class ContextBudget:
    """Token budget allocation for prompt construction.

    Based on 2,047 token hard limit for local NPU (input + output combined).
    We reserve tokens for output generation (including invisible think tags)
    so that growing conversation history doesn't starve the model's response.
    """

    max_tokens: int = 2047
    reserved_output_tokens: int = 512
    system_prompt_tokens: int = 180
    tool_description_tokens: int = 100
    memory_tokens: int = 120
    summary_tokens: int = 100
    recent_turns_tokens: int = 200
    user_message_tokens: int = 200

    @property
    def input_budget(self) -> int:
        """Max tokens available for input (system + history + user)."""
        return max(0, self.max_tokens - self.reserved_output_tokens)

    @property
    def generation_budget(self) -> int:
        """Tokens remaining for model generation."""
        used = (
            self.system_prompt_tokens
            + self.tool_description_tokens
            + self.memory_tokens
            + self.summary_tokens
            + self.recent_turns_tokens
            + self.user_message_tokens
        )
        return max(0, self.max_tokens - used)


@dataclass
class AssembledPrompt:
    """A fully constructed prompt ready for LLM inference.

    Built by ContextAssembler with priority-based component inclusion.
    """

    text: str  # The full prompt text
    estimated_tokens: int = 0
    has_tools: bool = False
    tool_names: list[str] = field(default_factory=list)
    has_memories: bool = False
    memory_count: int = 0
    has_summary: bool = False
    has_history: bool = False
    turns_included: int = 0
