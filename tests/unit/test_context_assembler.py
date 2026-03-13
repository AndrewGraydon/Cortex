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
    def test_fits_within_input_budget(self) -> None:
        asm = ContextAssembler()
        result = asm.assemble("Hello, how are you?")
        # Input budget is max_tokens - reserved_output_tokens (2047 - 512 = 1535)
        assert result.estimated_tokens <= ContextBudget().input_budget

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
        assert result.estimated_tokens <= ContextBudget().input_budget
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
        budget = ContextBudget(max_tokens=500, reserved_output_tokens=200)
        asm = ContextAssembler(budget=budget)
        result = asm.assemble("Hello")
        assert result.estimated_tokens <= budget.input_budget  # 300


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


class TestBuildMessages:
    """Tests for OpenAI-format messages output."""

    def test_minimal_system_and_user(self) -> None:
        asm = ContextAssembler()
        messages = asm.build_messages("Hello")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "Cortex" in messages[0]["content"]
        assert messages[1] == {"role": "user", "content": "Hello"}

    def test_with_history(self) -> None:
        history = [
            {"role": "user", "content": "What's the weather?"},
            {"role": "assistant", "content": "I can't check weather yet."},
        ]
        asm = ContextAssembler()
        messages = asm.build_messages("Can you try?", history=history)
        assert len(messages) == 4  # system + 2 history + user
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "What's the weather?"
        assert messages[2]["role"] == "assistant"
        assert messages[3] == {"role": "user", "content": "Can you try?"}

    def test_history_budget_trimming(self) -> None:
        budget = ContextBudget(
            max_tokens=100,
            system_prompt_tokens=50,
            user_message_tokens=30,
        )
        history = [
            {"role": "user", "content": "This is a very long message " * 20},
            {"role": "assistant", "content": "This is also very long " * 20},
        ]
        asm = ContextAssembler(budget=budget)
        messages = asm.build_messages("Hello", history=history)
        # History should be dropped or partially included
        assert len(messages) <= 4  # system + (0-2 history) + user
        assert messages[0]["role"] == "system"
        assert messages[-1] == {"role": "user", "content": "Hello"}

    def test_with_summary(self) -> None:
        asm = ContextAssembler()
        messages = asm.build_messages(
            "Continue",
            summary="We discussed weather earlier.",
        )
        assert len(messages) == 2
        assert "weather" in messages[0]["content"]
        assert "[Conversation summary]" in messages[0]["content"]

    def test_with_tools(self) -> None:
        tools = [ToolSchema(name="clock", description="Get current time")]
        asm = ContextAssembler()
        messages = asm.build_messages("What time?", tools=tools)
        assert "clock" in messages[0]["content"]
        assert "<tool_call>" in messages[0]["content"]

    def test_with_memories(self) -> None:
        memories = ["User's name is Andrew"]
        asm = ContextAssembler()
        messages = asm.build_messages("Hello", memories=memories)
        assert "Andrew" in messages[0]["content"]

    def test_newest_history_kept_when_tight(self) -> None:
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
        messages = asm.build_messages("Hello", history=history)
        # Check if recent messages are present
        contents = [m["content"] for m in messages]
        all_text = " ".join(contents)
        if len(messages) > 2:
            assert "RECENT" in all_text

    def test_message_order_preserved(self) -> None:
        history = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Second"},
            {"role": "user", "content": "Third"},
            {"role": "assistant", "content": "Fourth"},
        ]
        asm = ContextAssembler()
        messages = asm.build_messages("Fifth", history=history)
        # system, First, Second, Third, Fourth, Fifth
        roles = [m["role"] for m in messages]
        assert roles[0] == "system"
        assert roles[-1] == "user"
        # History should alternate user/assistant
        for i in range(1, len(messages) - 1, 2):
            assert messages[i]["role"] == "user"
            assert messages[i + 1]["role"] == "assistant"
