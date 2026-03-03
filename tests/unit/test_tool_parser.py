"""Tests for Hermes/NousFnCall tool call parser."""

from __future__ import annotations

from cortex.reasoning.tool_parser import HermesToolCallParser


class TestValidToolCalls:
    def test_single_tool_call(self) -> None:
        parser = HermesToolCallParser()
        text = '<tool_call>{"name": "clock", "arguments": {}}</tool_call>'
        clean, calls = parser.parse(text)
        assert len(calls) == 1
        assert calls[0].name == "clock"
        assert calls[0].arguments == {}
        assert clean == ""

    def test_tool_call_with_arguments(self) -> None:
        parser = HermesToolCallParser()
        text = (
            '<tool_call>{"name": "timer_set",'
            ' "arguments": {"duration": 300, "label": "tea"}}'
            "</tool_call>"
        )
        clean, calls = parser.parse(text)
        assert len(calls) == 1
        assert calls[0].name == "timer_set"
        assert calls[0].arguments["duration"] == 300
        assert calls[0].arguments["label"] == "tea"

    def test_tool_call_with_surrounding_text(self) -> None:
        parser = HermesToolCallParser()
        text = (
            "Let me check the time for you. "
            '<tool_call>{"name": "clock", "arguments": {}}</tool_call>'
            " One moment."
        )
        clean, calls = parser.parse(text)
        assert len(calls) == 1
        assert calls[0].name == "clock"
        assert "check the time" in clean
        assert "One moment" in clean
        assert "<tool_call>" not in clean

    def test_multiple_tool_calls(self) -> None:
        parser = HermesToolCallParser()
        text = (
            '<tool_call>{"name": "clock", "arguments": {}}</tool_call>'
            " "
            '<tool_call>{"name": "timer_set", "arguments": {"duration": 60}}</tool_call>'
        )
        clean, calls = parser.parse(text)
        assert len(calls) == 2
        assert calls[0].name == "clock"
        assert calls[1].name == "timer_set"

    def test_preserves_raw_text(self) -> None:
        parser = HermesToolCallParser()
        raw = '<tool_call>{"name": "clock", "arguments": {}}</tool_call>'
        _, calls = parser.parse(raw)
        assert calls[0].raw_text == raw


class TestNoToolCalls:
    def test_plain_text_passthrough(self) -> None:
        parser = HermesToolCallParser()
        text = "Hello, how can I help you today?"
        clean, calls = parser.parse(text)
        assert clean == text
        assert calls == []

    def test_empty_text(self) -> None:
        parser = HermesToolCallParser()
        clean, calls = parser.parse("")
        assert clean == ""
        assert calls == []

    def test_text_with_angle_brackets(self) -> None:
        parser = HermesToolCallParser()
        text = "The temperature is <70 degrees."
        clean, calls = parser.parse(text)
        assert clean == text
        assert calls == []


class TestMalformedToolCalls:
    def test_trailing_comma_in_json(self) -> None:
        parser = HermesToolCallParser()
        text = '<tool_call>{"name": "clock", "arguments": {},}</tool_call>'
        _, calls = parser.parse(text)
        assert len(calls) == 1
        assert calls[0].name == "clock"

    def test_single_quotes(self) -> None:
        parser = HermesToolCallParser()
        text = "<tool_call>{'name': 'clock', 'arguments': {}}</tool_call>"
        _, calls = parser.parse(text)
        assert len(calls) == 1
        assert calls[0].name == "clock"

    def test_missing_closing_brace(self) -> None:
        parser = HermesToolCallParser()
        text = '<tool_call>{"name": "clock", "arguments": {}</tool_call>'
        _, calls = parser.parse(text)
        assert len(calls) == 1
        assert calls[0].name == "clock"

    def test_missing_name_field(self) -> None:
        parser = HermesToolCallParser()
        text = '<tool_call>{"arguments": {"x": 1}}</tool_call>'
        _, calls = parser.parse(text)
        assert len(calls) == 0

    def test_completely_invalid_json(self) -> None:
        parser = HermesToolCallParser()
        text = "<tool_call>not json at all</tool_call>"
        _, calls = parser.parse(text)
        assert len(calls) == 0

    def test_arguments_as_string(self) -> None:
        parser = HermesToolCallParser()
        text = '<tool_call>{"name": "clock", "arguments": "{}"}</tool_call>'
        _, calls = parser.parse(text)
        assert len(calls) == 1
        assert calls[0].arguments == {}

    def test_whitespace_in_tags(self) -> None:
        parser = HermesToolCallParser()
        text = '<tool_call> {"name": "clock", "arguments": {}} </tool_call>'
        _, calls = parser.parse(text)
        assert len(calls) == 1
        assert calls[0].name == "clock"

    def test_multiline_tool_call(self) -> None:
        parser = HermesToolCallParser()
        text = '<tool_call>\n{"name": "timer_set",\n"arguments": {"duration": 60}}\n</tool_call>'
        _, calls = parser.parse(text)
        assert len(calls) == 1
        assert calls[0].name == "timer_set"
        assert calls[0].arguments["duration"] == 60


class TestCleanTextOutput:
    def test_clean_text_removes_all_markup(self) -> None:
        parser = HermesToolCallParser()
        text = 'Sure! <tool_call>{"name": "clock", "arguments": {}}</tool_call> Here is the time.'
        clean, _ = parser.parse(text)
        assert "<tool_call>" not in clean
        assert "</tool_call>" not in clean
        assert "Sure!" in clean
        assert "Here is the time." in clean

    def test_multiple_newlines_collapsed(self) -> None:
        parser = HermesToolCallParser()
        text = (
            "Text before.\n\n\n"
            '<tool_call>{"name": "clock", "arguments": {}}</tool_call>'
            "\n\n\nText after."
        )
        clean, _ = parser.parse(text)
        # Should not have 3+ consecutive newlines
        assert "\n\n\n" not in clean
