"""Tests for reasoning layer data types."""

from __future__ import annotations

from cortex.reasoning.types import AssembledPrompt, ContextBudget, ToolSchema


class TestToolSchema:
    def test_basic_schema(self) -> None:
        schema = ToolSchema(name="clock", description="Get current time/date")
        assert schema.name == "clock"
        assert schema.parameters == {}

    def test_to_dict_no_params(self) -> None:
        schema = ToolSchema(name="clock", description="Get current time/date")
        d = schema.to_dict()
        assert d == {"name": "clock", "description": "Get current time/date"}
        assert "parameters" not in d

    def test_to_dict_with_params(self) -> None:
        schema = ToolSchema(
            name="timer_set",
            description="Set countdown timer",
            parameters={
                "duration": {"type": "integer", "description": "seconds"},
                "label": {"type": "string"},
            },
        )
        d = schema.to_dict()
        assert d["name"] == "timer_set"
        assert d["parameters"]["type"] == "object"
        assert "duration" in d["parameters"]["properties"]
        assert "label" in d["parameters"]["properties"]

    def test_frozen(self) -> None:
        schema = ToolSchema(name="clock", description="test")
        try:
            schema.name = "other"  # type: ignore[misc]
            raise AssertionError("Should be frozen")
        except AttributeError:
            pass


class TestContextBudget:
    def test_default_budget(self) -> None:
        budget = ContextBudget()
        assert budget.max_tokens == 2047
        assert budget.reserved_output_tokens == 512

    def test_input_budget(self) -> None:
        budget = ContextBudget()
        # 2047 - 512 = 1535
        assert budget.input_budget == 1535

    def test_input_budget_custom(self) -> None:
        budget = ContextBudget(max_tokens=2047, reserved_output_tokens=512)
        assert budget.input_budget == 1535

    def test_input_budget_never_negative(self) -> None:
        budget = ContextBudget(max_tokens=100, reserved_output_tokens=200)
        assert budget.input_budget == 0

    def test_generation_budget(self) -> None:
        budget = ContextBudget()
        # 2047 - (180 + 100 + 120 + 100 + 200 + 200) = 2047 - 900 = 1147
        assert budget.generation_budget == 1147

    def test_custom_budget(self) -> None:
        budget = ContextBudget(
            max_tokens=2047,
            system_prompt_tokens=150,
            tool_description_tokens=0,  # No tools
            memory_tokens=0,  # No memories
            summary_tokens=0,
            recent_turns_tokens=0,
            user_message_tokens=100,
        )
        assert budget.generation_budget == 2047 - 150 - 100

    def test_generation_budget_never_negative(self) -> None:
        budget = ContextBudget(
            max_tokens=100,
            system_prompt_tokens=200,  # Exceeds max
        )
        assert budget.generation_budget == 0


class TestAssembledPrompt:
    def test_simple_prompt(self) -> None:
        prompt = AssembledPrompt(text="You are Cortex. User: Hello")
        assert prompt.text == "You are Cortex. User: Hello"
        assert prompt.estimated_tokens == 0
        assert not prompt.has_tools
        assert not prompt.has_memories
        assert not prompt.has_summary
        assert not prompt.has_history
        assert prompt.tool_names == []

    def test_full_prompt(self) -> None:
        prompt = AssembledPrompt(
            text="Full prompt text here...",
            estimated_tokens=750,
            has_tools=True,
            tool_names=["clock", "timer_set"],
            has_memories=True,
            memory_count=3,
            has_summary=True,
            has_history=True,
            turns_included=1,
        )
        assert prompt.estimated_tokens == 750
        assert len(prompt.tool_names) == 2
        assert prompt.memory_count == 3
        assert prompt.turns_included == 1
