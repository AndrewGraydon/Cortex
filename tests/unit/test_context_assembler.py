"""Tests for context assembler — priority-based prompt construction."""

from __future__ import annotations

from cortex.reasoning.context_assembler import ContextAssembler
from cortex.reasoning.types import ContextBudget, ToolSchema


class TestBasicAssembly:
    def test_simple_user_message(self) -> None:
        asm = ContextAssembler()
        result = asm.assemble("Hello")
        assert "Cortex" in result.text  # System prompt included
        assert "Hello" in result.text  # User message included
        assert "Assistant:" in result.text  # Response marker
        assert not result.has_tools
        assert not result.has_memories
        assert result.estimated_tokens > 0

    def test_with_tools(self) -> None:
        tools = [ToolSchema(name="clock", description="Get current time")]
        asm = ContextAssembler()
        result = asm.assemble("What time is it?", tools=tools)
        assert result.has_tools
        assert result.tool_names == ["clock"]
        assert "clock" in result.text
        assert "<tool_call>" in result.text  # Tool instruction included

    def test_with_memories(self) -> None:
        memories = ["User's name is Andrew"]
        asm = ContextAssembler()
        result = asm.assemble("Hello", memories=memories)
        assert result.has_memories
        assert result.memory_count == 1
        assert "Andrew" in result.text

    def test_with_summary(self) -> None:
        asm = ContextAssembler()
        result = asm.assemble(
            "Continue our discussion",
            summary="Previously discussed weather and temperatures.",
        )
        assert result.has_summary
        assert "weather" in result.text

    def test_with_history(self) -> None:
        history = [
            {"role": "user", "content": "What's the weather?"},
            {"role": "assistant", "content": "I don't have weather access yet."},
        ]
        asm = ContextAssembler()
        result = asm.assemble("Can you check?", history=history)
        assert result.has_history
        assert result.turns_included == 2
        assert "weather" in result.text


class TestBudgetEnforcement:
    def test_fits_within_default_budget(self) -> None:
        asm = ContextAssembler()
        result = asm.assemble("Hello, how are you?")
        assert result.estimated_tokens <= 2047

    def test_with_all_components_fits(self) -> None:
        tools = [
            ToolSchema(name="clock", description="Get current time"),
            ToolSchema(
                name="timer_set",
                description="Set timer",
                parameters={"duration": {"type": "integer"}},
            ),
        ]
        memories = ["User's name is Andrew", "Prefers concise answers"]
        history = [
            {"role": "user", "content": "Set a timer"},
            {"role": "assistant", "content": "For how long?"},
        ]
        asm = ContextAssembler()
        result = asm.assemble(
            "Five minutes please",
            tools=tools,
            memories=memories,
            summary="Setting up a timer.",
            history=history,
        )
        assert result.estimated_tokens <= 2047
        assert result.has_tools
        assert result.has_memories
        assert result.has_summary
        assert result.has_history

    def test_history_dropped_when_budget_tight(self) -> None:
        # Create a very tight budget
        budget = ContextBudget(
            max_tokens=100,
            system_prompt_tokens=50,
            user_message_tokens=30,
        )
        # Long history that won't fit
        history = [
            {"role": "user", "content": "This is a long message " * 20},
            {"role": "assistant", "content": "This is also long " * 20},
        ]
        asm = ContextAssembler(budget=budget)
        result = asm.assemble("Hello", history=history)
        # History should be dropped or partially included
        assert result.turns_included < 2

    def test_custom_budget(self) -> None:
        budget = ContextBudget(max_tokens=500)
        asm = ContextAssembler(budget=budget)
        result = asm.assemble("Hello")
        assert result.estimated_tokens <= 500


class TestPriorityOrder:
    def test_system_prompt_always_present(self) -> None:
        asm = ContextAssembler()
        result = asm.assemble("Hello")
        assert "Cortex" in result.text

    def test_user_message_always_present(self) -> None:
        asm = ContextAssembler()
        result = asm.assemble("specific test phrase")
        assert "specific test phrase" in result.text

    def test_response_marker_at_end(self) -> None:
        asm = ContextAssembler()
        result = asm.assemble("Hello")
        assert result.text.endswith("Assistant:")

    def test_history_newest_first_kept(self) -> None:
        # With tight budget, newest turns should be kept
        budget = ContextBudget(
            max_tokens=300,
            system_prompt_tokens=60,
            user_message_tokens=30,
        )
        history = [
            {"role": "user", "content": "OLD: " + "word " * 30},
            {"role": "assistant", "content": "OLD REPLY: " + "word " * 30},
            {"role": "user", "content": "RECENT: short"},
            {"role": "assistant", "content": "RECENT REPLY: short"},
        ]
        asm = ContextAssembler(budget=budget)
        result = asm.assemble("Hello", history=history)
        # Recent turns should be present; old ones may be dropped
        if result.has_history:
            assert "RECENT" in result.text


class TestMetadata:
    def test_tool_names_tracked(self) -> None:
        tools = [
            ToolSchema(name="clock", description="time"),
            ToolSchema(name="calc", description="math"),
        ]
        asm = ContextAssembler()
        result = asm.assemble("test", tools=tools)
        assert set(result.tool_names) == {"clock", "calc"}

    def test_memory_count_tracked(self) -> None:
        memories = ["fact 1", "fact 2", "fact 3"]
        asm = ContextAssembler()
        result = asm.assemble("test", memories=memories)
        assert result.memory_count == 3

    def test_no_components_metadata(self) -> None:
        asm = ContextAssembler()
        result = asm.assemble("test")
        assert not result.has_tools
        assert not result.has_memories
        assert not result.has_summary
        assert not result.has_history
        assert result.tool_names == []
        assert result.memory_count == 0
        assert result.turns_included == 0
