"""Tests for agent framework data types."""

from __future__ import annotations

from cortex.agent.types import (
    ActionRequest,
    ActionResult,
    AgentResponse,
    IntentMatch,
    IntentType,
    RoutingDecision,
    ToolCall,
    ToolResult,
)


class TestIntentType:
    def test_all_types_exist(self) -> None:
        expected = {"utility", "llm", "farewell"}
        actual = {t.value for t in IntentType}
        assert actual == expected


class TestIntentMatch:
    def test_basic_construction(self) -> None:
        m = IntentMatch(intent_id="clock", intent_type=IntentType.UTILITY)
        assert m.intent_id == "clock"
        assert m.intent_type == IntentType.UTILITY
        assert m.tool_hint is None
        assert m.extracted == {}

    def test_with_tool_hint_and_captures(self) -> None:
        m = IntentMatch(
            intent_id="timer_set",
            intent_type=IntentType.UTILITY,
            tool_hint="timer_set",
            extracted={"duration": "5", "unit": "minutes"},
        )
        assert m.tool_hint == "timer_set"
        assert m.extracted["duration"] == "5"

    def test_frozen(self) -> None:
        m = IntentMatch(intent_id="clock", intent_type=IntentType.UTILITY)
        try:
            m.intent_id = "other"  # type: ignore[misc]
            raise AssertionError("Should be frozen")
        except AttributeError:
            pass


class TestRoutingDecision:
    def test_llm_fallback(self) -> None:
        d = RoutingDecision(intent_type=IntentType.LLM)
        assert d.intent_match is None
        assert d.tool_hints == []

    def test_utility_with_match(self) -> None:
        match = IntentMatch(intent_id="clock", intent_type=IntentType.UTILITY)
        d = RoutingDecision(
            intent_type=IntentType.UTILITY,
            intent_match=match,
            tool_hints=["clock"],
        )
        assert d.intent_match is match
        assert d.tool_hints == ["clock"]


class TestToolCall:
    def test_basic_tool_call(self) -> None:
        tc = ToolCall(name="clock")
        assert tc.name == "clock"
        assert tc.arguments == {}
        assert tc.raw_text == ""

    def test_with_arguments(self) -> None:
        tc = ToolCall(
            name="timer_set",
            arguments={"duration": 300, "label": "tea"},
            raw_text='<tool_call>{"name":"timer_set"}</tool_call>',
        )
        assert tc.arguments["duration"] == 300
        assert "tool_call" in tc.raw_text

    def test_frozen(self) -> None:
        tc = ToolCall(name="clock")
        try:
            tc.name = "other"  # type: ignore[misc]
            raise AssertionError("Should be frozen")
        except AttributeError:
            pass


class TestToolResult:
    def test_success(self) -> None:
        r = ToolResult(tool_name="clock", success=True, data="14:30", display_text="It's 2:30 PM")
        assert r.success
        assert r.error is None
        assert r.display_text == "It's 2:30 PM"

    def test_failure(self) -> None:
        r = ToolResult(tool_name="timer_set", success=False, error="Invalid duration")
        assert not r.success
        assert r.error == "Invalid duration"


class TestActionRequest:
    def test_defaults(self) -> None:
        req = ActionRequest(action_id="timer_set")
        assert req.source == "voice"
        assert req.parameters == {}

    def test_with_params(self) -> None:
        req = ActionRequest(
            action_id="timer_set",
            parameters={"duration": 300},
            source="scheduled",
        )
        assert req.source == "scheduled"
        assert req.parameters["duration"] == 300


class TestActionResult:
    def test_success(self) -> None:
        res = ActionResult(action_id="timer_set", success=True, display_text="Timer set for 5 min")
        assert res.success
        assert res.display_text == "Timer set for 5 min"

    def test_failure(self) -> None:
        res = ActionResult(action_id="timer_set", success=False, error="Too many active timers")
        assert not res.success


class TestAgentResponse:
    def test_simple_text_response(self) -> None:
        resp = AgentResponse(text="Hello there!")
        assert resp.text == "Hello there!"
        assert resp.tool_calls == []
        assert resp.tool_results == []
        assert not resp.used_llm
        assert resp.intent_id is None

    def test_utility_response(self) -> None:
        resp = AgentResponse(
            text="It's 2:30 PM",
            used_llm=False,
            intent_id="clock",
            tool_results=[ToolResult(tool_name="clock", success=True, data="14:30")],
        )
        assert not resp.used_llm
        assert resp.intent_id == "clock"
        assert len(resp.tool_results) == 1

    def test_llm_with_tool_response(self) -> None:
        tc = ToolCall(name="timer_set", arguments={"duration": 300})
        tr = ToolResult(tool_name="timer_set", success=True, display_text="Timer set")
        resp = AgentResponse(
            text="I've set a 5 minute timer for you.",
            tool_calls=[tc],
            tool_results=[tr],
            used_llm=True,
        )
        assert resp.used_llm
        assert len(resp.tool_calls) == 1
        assert len(resp.tool_results) == 1
