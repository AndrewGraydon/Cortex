"""Reasoning layer protocol interfaces — context assembly and tool call parsing."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from cortex.agent.types import ToolCall
from cortex.reasoning.types import AssembledPrompt, ToolSchema


@runtime_checkable
class ContextAssembler(Protocol):
    """Builds token-budgeted prompts with priority-based component inclusion.

    Priority order (P1 highest, P7 lowest):
      P1: System prompt (always included)
      P2: Current user message (always included)
      P3: Tool descriptions (only relevant tools)
      P4: Retrieved memories (auto-injected)
      P5: Conversation summary
      P6: Recent turns (last 1 exchange)
      P7: Older history (dropped at 2,047 limit)
    """

    def assemble(
        self,
        user_message: str,
        tools: list[ToolSchema] | None = None,
        memories: list[str] | None = None,
        summary: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> AssembledPrompt:
        """Assemble a prompt within the token budget."""
        ...


@runtime_checkable
class ToolCallParser(Protocol):
    """Parses tool calls from LLM output text."""

    def parse(self, text: str) -> tuple[str, list[ToolCall]]:
        """Parse LLM output into plain text and tool calls.

        Returns (clean_text, tool_calls) where clean_text has
        tool call markup removed.
        """
        ...
