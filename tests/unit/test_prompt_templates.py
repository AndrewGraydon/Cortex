"""Tests for system prompt templates."""

from __future__ import annotations

from cortex.reasoning.prompt_templates import (
    SYSTEM_PROMPT_V1,
    TOOL_INSTRUCTION,
    build_system_prompt,
    build_tool_descriptions,
)
from cortex.reasoning.token_counter import estimate_tokens
from cortex.reasoning.types import ToolSchema


class TestSystemPromptV1:
    def test_contains_identity(self) -> None:
        assert "Cortex" in SYSTEM_PROMPT_V1

    def test_concise(self) -> None:
        tokens = estimate_tokens(SYSTEM_PROMPT_V1)
        # Must be very short — complex prompts trigger Qwen3's thinking mode
        assert tokens <= 20


class TestToolInstruction:
    def test_contains_format(self) -> None:
        assert "<tool_call>" in TOOL_INSTRUCTION
        assert "tool_name" in TOOL_INSTRUCTION

    def test_concise(self) -> None:
        tokens = estimate_tokens(TOOL_INSTRUCTION)
        assert tokens <= 80


class TestBuildToolDescriptions:
    def test_empty_tools(self) -> None:
        assert build_tool_descriptions([]) == ""

    def test_single_tool_no_params(self) -> None:
        tools = [ToolSchema(name="clock", description="Get current time/date")]
        desc = build_tool_descriptions(tools)
        assert "clock" in desc
        assert "current time" in desc

    def test_tool_with_params(self) -> None:
        tools = [
            ToolSchema(
                name="timer_set",
                description="Set countdown timer",
                parameters={
                    "duration": {"type": "integer", "description": "seconds"},
                    "label": {"type": "string"},
                },
            )
        ]
        desc = build_tool_descriptions(tools)
        assert "timer_set" in desc
        assert "duration(integer)" in desc
        assert "label(string)" in desc

    def test_multiple_tools(self) -> None:
        tools = [
            ToolSchema(name="clock", description="Get current time"),
            ToolSchema(name="calculator", description="Evaluate math"),
        ]
        desc = build_tool_descriptions(tools)
        assert "clock" in desc
        assert "calculator" in desc


class TestBuildSystemPrompt:
    def test_base_prompt_only(self) -> None:
        prompt = build_system_prompt()
        assert "Cortex" in prompt
        assert "<tool_call>" not in prompt
        assert "[Memory]" not in prompt

    def test_with_tools(self) -> None:
        tools = [ToolSchema(name="clock", description="Get current time")]
        prompt = build_system_prompt(tools=tools)
        assert "Cortex" in prompt
        assert "<tool_call>" in prompt
        assert "clock" in prompt

    def test_with_memories(self) -> None:
        memories = ["User's name is Andrew", "User prefers concise answers"]
        prompt = build_system_prompt(memories=memories)
        assert "[Memory]" in prompt
        assert "Andrew" in prompt
        assert "concise" in prompt

    def test_with_tools_and_memories(self) -> None:
        tools = [ToolSchema(name="clock", description="Get current time")]
        memories = ["User's name is Andrew"]
        prompt = build_system_prompt(tools=tools, memories=memories)
        assert "<tool_call>" in prompt
        assert "clock" in prompt
        assert "[Memory]" in prompt
        assert "Andrew" in prompt

    def test_total_budget_reasonable(self) -> None:
        tools = [
            ToolSchema(name="clock", description="Get current time"),
            ToolSchema(
                name="timer_set",
                description="Set timer",
                parameters={"duration": {"type": "integer"}, "label": {"type": "string"}},
            ),
        ]
        memories = ["User name is Andrew", "Prefers 22C", "Lives in Vancouver"]
        prompt = build_system_prompt(tools=tools, memories=memories)
        tokens = estimate_tokens(prompt)
        # System + tools + memories should fit in ~400 tokens
        assert tokens <= 400
