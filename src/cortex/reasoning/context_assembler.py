"""Context assembler — builds token-budgeted prompts.

Implements priority-based component inclusion for the 2,047 token budget:
  P1: System prompt (always included)
  P2: Current user message (always included)
  P3: Tool descriptions (only relevant tools)
  P4: Retrieved memories (auto-injected)
  P5: Conversation summary
  P6: Recent turns (last 1 exchange)
  P7: Older history (dropped first at budget)

Respects AX8850 p128 block alignment for efficient NPU processing.
"""

from __future__ import annotations

import logging

from cortex.reasoning.prompt_templates import build_system_prompt
from cortex.reasoning.token_counter import estimate_tokens
from cortex.reasoning.types import AssembledPrompt, ContextBudget, ToolSchema

logger = logging.getLogger(__name__)


class ContextAssembler:
    """Builds prompts that fit within the NPU token budget.

    Components are added in priority order. Lower-priority components
    are dropped if the budget is exceeded.
    """

    def __init__(self, budget: ContextBudget | None = None) -> None:
        self._budget = budget or ContextBudget()

    def assemble(
        self,
        user_message: str,
        tools: list[ToolSchema] | None = None,
        memories: list[str] | None = None,
        knowledge_passage: str | None = None,
        summary: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> AssembledPrompt:
        """Assemble a prompt within the token budget.

        Args:
            user_message: The current user utterance (P2).
            tools: Tool schemas to include (P3).
            memories: Retrieved memory strings (P4).
            knowledge_passage: RAG passage from knowledge store (P4.5).
            summary: Conversation summary (P5).
            history: Recent conversation turns as role/content dicts (P6-P7).

        Returns:
            AssembledPrompt with the full text and metadata.
        """
        input_budget = self._budget.input_budget
        used_tokens = 0

        # --- P1: System prompt (always included) ---
        system_prompt = build_system_prompt(
            tools=tools,
            memories=memories,
        )
        system_tokens = estimate_tokens(system_prompt)
        used_tokens += system_tokens

        # --- P2: User message (always included) ---
        user_block = f"\nUser: {user_message}"
        user_tokens = estimate_tokens(user_block)
        used_tokens += user_tokens

        # Track what we've included
        has_tools = bool(tools)
        tool_names = [t.name for t in tools] if tools else []
        has_memories = bool(memories)
        memory_count = len(memories) if memories else 0
        has_summary = False
        has_history = False
        turns_included = 0

        # --- Build middle sections (P4.5-P7, budget permitting) ---
        middle_parts: list[str] = []

        # P4.5: Knowledge passage (RAG result)
        if knowledge_passage:
            knowledge_block = f"\n{knowledge_passage}"
            knowledge_tokens = estimate_tokens(knowledge_block)
            if used_tokens + knowledge_tokens <= input_budget - self._budget.user_message_tokens:
                middle_parts.append(knowledge_block)
                used_tokens += knowledge_tokens

        # P5: Conversation summary
        if summary:
            summary_block = f"\n[Summary] {summary}"
            summary_tokens = estimate_tokens(summary_block)
            if used_tokens + summary_tokens <= input_budget - self._budget.user_message_tokens:
                middle_parts.append(summary_block)
                used_tokens += summary_tokens
                has_summary = True

        # P6-P7: Recent history (newest first, drop oldest)
        if history:
            history_parts: list[str] = []
            for turn in reversed(history):
                role = turn.get("role", "user")
                content = turn.get("content", "")
                turn_block = f"\n{role.capitalize()}: {content}"
                turn_tokens = estimate_tokens(turn_block)
                if used_tokens + turn_tokens <= input_budget - self._budget.user_message_tokens:
                    history_parts.insert(0, turn_block)
                    used_tokens += turn_tokens
                    turns_included += 1
                    has_history = True
                else:
                    break  # Budget exhausted for history

            middle_parts.extend(history_parts)

        # --- Assemble final prompt ---
        prompt_text = system_prompt
        for part in middle_parts:
            prompt_text += part
        prompt_text += user_block
        prompt_text += "\nAssistant:"

        total_tokens = estimate_tokens(prompt_text)

        if total_tokens > input_budget:
            logger.warning(
                "Prompt exceeds input budget: %d > %d tokens (estimate)",
                total_tokens,
                input_budget,
            )

        return AssembledPrompt(
            text=prompt_text,
            estimated_tokens=total_tokens,
            has_tools=has_tools,
            tool_names=tool_names,
            has_memories=has_memories,
            memory_count=memory_count,
            has_summary=has_summary,
            has_history=has_history,
            turns_included=turns_included,
        )

    def build_messages(
        self,
        user_message: str,
        tools: list[ToolSchema] | None = None,
        memories: list[str] | None = None,
        summary: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        """Build OpenAI-format messages array within token budget.

        Same priority scheme as assemble(), but returns structured messages
        for the VLM's OpenAI-compatible /v1/chat/completions API.

        Returns:
            List of {"role": ..., "content": ...} dicts:
            [system, *history_turns, user].
        """
        input_budget = self._budget.input_budget
        used_tokens = 0

        # P1: System prompt (always included)
        system_content = build_system_prompt(tools=tools, memories=memories)
        used_tokens += estimate_tokens(system_content)

        # P2: User message (always included)
        used_tokens += estimate_tokens(user_message)

        # P5: Summary appended to system prompt if fits
        if summary:
            summary_block = f"\n\n[Conversation summary] {summary}"
            summary_tokens = estimate_tokens(summary_block)
            if used_tokens + summary_tokens <= input_budget - self._budget.user_message_tokens:
                system_content += summary_block
                used_tokens += summary_tokens

        # P6-P7: History turns (newest first, drop oldest)
        history_messages: list[dict[str, str]] = []
        if history:
            for turn in reversed(history):
                content = turn.get("content", "")
                turn_tokens = estimate_tokens(content)
                if used_tokens + turn_tokens <= input_budget - self._budget.user_message_tokens:
                    history_messages.insert(0, turn)
                    used_tokens += turn_tokens
                else:
                    break

        # Assemble messages array
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_content},
        ]
        messages.extend(history_messages)
        messages.append({"role": "user", "content": user_message})

        logger.debug(
            "Context: %d messages, ~%d input tokens (budget %d, output reserve %d)",
            len(messages),
            used_tokens,
            input_budget,
            self._budget.reserved_output_tokens,
        )
        return messages
