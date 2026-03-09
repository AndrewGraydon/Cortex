"""Tests for episodic event extraction from interactions."""

from __future__ import annotations

from cortex.memory.extraction import extract_episodic_events
from cortex.memory.types import EventType


class TestExtractToolUse:
    def test_no_tool_calls(self) -> None:
        events = extract_episodic_events(tool_calls=None)
        assert events == []

    def test_empty_tool_calls(self) -> None:
        events = extract_episodic_events(tool_calls=[])
        assert events == []

    def test_single_tool_call(self) -> None:
        events = extract_episodic_events(
            tool_calls=[{"name": "clock", "arguments": "{}"}],
            session_id="sess-1",
        )
        assert len(events) == 1
        assert events[0].event_type == EventType.TOOL_USE
        assert events[0].content == "clock"
        assert events[0].session_id == "sess-1"

    def test_multiple_tool_calls(self) -> None:
        events = extract_episodic_events(
            tool_calls=[
                {"name": "clock", "arguments": "{}"},
                {"name": "calculator", "arguments": '{"expr": "2+2"}'},
            ]
        )
        assert len(events) == 2
        assert events[0].content == "clock"
        assert events[1].content == "calculator"

    def test_tool_metadata_preserved(self) -> None:
        events = extract_episodic_events(
            tool_calls=[{"name": "timer", "arguments": '{"duration": 300}'}]
        )
        assert events[0].metadata["arguments"] == '{"duration": 300}'


class TestExtractTopics:
    def test_no_messages(self) -> None:
        events = extract_episodic_events(user_messages=None)
        assert events == []

    def test_empty_messages(self) -> None:
        events = extract_episodic_events(user_messages=[])
        assert events == []

    def test_weather_topic(self) -> None:
        events = extract_episodic_events(user_messages=["What's the weather like today?"])
        topic_events = [e for e in events if e.event_type == EventType.QUERY_TOPIC]
        assert len(topic_events) >= 1
        assert any(e.content == "weather" for e in topic_events)

    def test_multiple_topics(self) -> None:
        events = extract_episodic_events(
            user_messages=["Set a timer for 5 minutes", "What's the weather?"]
        )
        topic_events = [e for e in events if e.event_type == EventType.QUERY_TOPIC]
        contents = {e.content for e in topic_events}
        assert "timer" in contents
        assert "weather" in contents

    def test_no_matching_topics(self) -> None:
        events = extract_episodic_events(user_messages=["Tell me a joke"])
        topic_events = [e for e in events if e.event_type == EventType.QUERY_TOPIC]
        assert len(topic_events) == 0

    def test_deduplicates_topics(self) -> None:
        events = extract_episodic_events(
            user_messages=["What's the weather?", "How about the weather tomorrow?"]
        )
        topic_events = [e for e in events if e.event_type == EventType.QUERY_TOPIC]
        weather_events = [e for e in topic_events if e.content == "weather"]
        assert len(weather_events) == 1  # Deduplicated


class TestCombined:
    def test_tool_and_topic_events(self) -> None:
        events = extract_episodic_events(
            tool_calls=[{"name": "clock", "arguments": "{}"}],
            user_messages=["What time is it?"],
            session_id="sess-1",
        )
        tool_events = [e for e in events if e.event_type == EventType.TOOL_USE]
        topic_events = [e for e in events if e.event_type == EventType.QUERY_TOPIC]
        assert len(tool_events) == 1
        assert len(topic_events) >= 1
        assert all(e.session_id == "sess-1" for e in events)
