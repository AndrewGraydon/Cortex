"""Tests for briefing builder."""

from __future__ import annotations

from cortex.agent.proactive.briefing import BriefingBuilder
from cortex.agent.proactive.types import ProactiveType, RoutinePattern


class TestBriefingBuilder:
    def test_empty_briefing(self) -> None:
        builder = BriefingBuilder()
        result = builder.build()
        assert result.proactive_type == ProactiveType.MORNING_BRIEFING
        assert result.title == "Morning Briefing"
        assert "No calendar events" in result.message

    def test_with_calendar_events(self) -> None:
        builder = BriefingBuilder()
        events = [
            {"summary": "Team standup", "start_time": "09:00"},
            {"summary": "Lunch meeting", "start_time": "12:00"},
        ]
        result = builder.build(calendar_events=events)
        assert "Team standup" in result.message
        assert "Lunch meeting" in result.message

    def test_with_reminders(self) -> None:
        builder = BriefingBuilder()
        result = builder.build(reminders=["Take medicine", "Call dentist"])
        assert "Take medicine" in result.message
        assert "Call dentist" in result.message

    def test_with_patterns(self) -> None:
        builder = BriefingBuilder()
        patterns = [
            RoutinePattern(
                event_type="tool_use",
                content="clock",
                hour=8,
                day_of_week=1,
                count=10,
            )
        ]
        result = builder.build(patterns=patterns)
        assert "clock" in result.message
        assert "routines" in result.message.lower()

    def test_combined_briefing(self) -> None:
        builder = BriefingBuilder()
        result = builder.build(
            calendar_events=[{"summary": "Meeting"}],
            reminders=["Reminder"],
            patterns=[
                RoutinePattern(
                    event_type="tool_use",
                    content="weather",
                    hour=8,
                    day_of_week=1,
                    count=5,
                )
            ],
        )
        assert "Meeting" in result.message
        assert "Reminder" in result.message
        assert "weather" in result.message

    def test_priority_is_normal(self) -> None:
        builder = BriefingBuilder()
        result = builder.build()
        assert result.priority == 2

    def test_limits_patterns_to_three(self) -> None:
        builder = BriefingBuilder()
        patterns = [
            RoutinePattern(
                event_type="tool_use", content=f"tool-{i}", hour=8, day_of_week=1, count=5
            )
            for i in range(5)
        ]
        result = builder.build(patterns=patterns)
        # Should only include first 3 patterns
        assert "tool-0" in result.message
        assert "tool-2" in result.message
        assert "tool-4" not in result.message
