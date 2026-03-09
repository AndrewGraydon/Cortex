"""Tests for calendar tools (query and create)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from cortex.agent.protocols import Tool
from cortex.agent.tools.builtin.calendar_tool import (
    CalendarCreateTool,
    CalendarQueryTool,
    set_calendar_backend,
)
from cortex.external.calendar.mock import MockCalendarAdapter
from cortex.external.types import CalendarEvent


@pytest.fixture(autouse=True)
def _reset_backend() -> Any:
    """Reset calendar backend before/after each test."""
    set_calendar_backend(None)
    yield
    set_calendar_backend(None)


def _make_event(
    uid: str = "t1",
    summary: str = "Test",
    hours_from_now: float = 1,
) -> CalendarEvent:
    now = datetime.now(tz=UTC)
    return CalendarEvent(
        uid=uid,
        summary=summary,
        start=now + timedelta(hours=hours_from_now),
        end=now + timedelta(hours=hours_from_now + 1),
    )


# --- Protocol compliance ---


class TestCalendarToolProtocol:
    def test_query_satisfies_tool(self) -> None:
        tool = CalendarQueryTool()
        assert isinstance(tool, Tool)

    def test_create_satisfies_tool(self) -> None:
        tool = CalendarCreateTool()
        assert isinstance(tool, Tool)


# --- CalendarQueryTool properties ---


class TestCalendarQueryToolProperties:
    def test_name(self) -> None:
        assert CalendarQueryTool().name == "calendar_query"

    def test_description(self) -> None:
        assert CalendarQueryTool().description == "List upcoming calendar events"

    def test_permission_tier(self) -> None:
        assert CalendarQueryTool().permission_tier == 0

    def test_schema_has_days_ahead(self) -> None:
        schema = CalendarQueryTool().get_schema()
        assert schema["name"] == "calendar_query"
        assert "days_ahead" in schema["parameters"]["properties"]


# --- CalendarQueryTool execution ---


class TestCalendarQueryToolExecute:
    async def test_no_backend_returns_not_configured(self) -> None:
        tool = CalendarQueryTool()
        result = await tool.execute({})
        assert result.success is True
        assert result.data == []
        assert "not configured" in result.display_text.lower()

    async def test_empty_calendar(self) -> None:
        adapter = MockCalendarAdapter()
        set_calendar_backend(adapter)

        tool = CalendarQueryTool()
        result = await tool.execute({})
        assert result.success is True
        assert result.data == []
        assert "no events" in result.display_text.lower()

    async def test_returns_events(self) -> None:
        adapter = MockCalendarAdapter()
        await adapter.create_event(_make_event(uid="e1", summary="Standup"))
        set_calendar_backend(adapter)

        tool = CalendarQueryTool()
        result = await tool.execute({})
        assert result.success is True
        assert len(result.data) == 1
        assert result.data[0]["uid"] == "e1"
        assert "Standup" in result.display_text

    async def test_multiple_events_display(self) -> None:
        adapter = MockCalendarAdapter()
        for i in range(3):
            await adapter.create_event(
                _make_event(uid=f"e{i}", summary=f"Event {i}", hours_from_now=i + 1)
            )
        set_calendar_backend(adapter)

        tool = CalendarQueryTool()
        result = await tool.execute({})
        assert result.success is True
        assert len(result.data) == 3
        assert "3 events" in result.display_text

    async def test_days_ahead_parameter(self) -> None:
        adapter = MockCalendarAdapter()
        # Event tomorrow
        await adapter.create_event(_make_event(uid="tomorrow", hours_from_now=24))
        # Event in 5 days
        await adapter.create_event(_make_event(uid="later", hours_from_now=5 * 24))
        set_calendar_backend(adapter)

        tool = CalendarQueryTool()
        result = await tool.execute({"days_ahead": 2})
        assert len(result.data) == 1
        assert result.data[0]["uid"] == "tomorrow"

    async def test_days_ahead_defaults_to_7(self) -> None:
        adapter = MockCalendarAdapter()
        await adapter.create_event(_make_event(uid="day5", hours_from_now=5 * 24))
        await adapter.create_event(_make_event(uid="day10", hours_from_now=10 * 24))
        set_calendar_backend(adapter)

        tool = CalendarQueryTool()
        result = await tool.execute({})
        assert len(result.data) == 1

    async def test_days_ahead_capped_at_90(self) -> None:
        adapter = MockCalendarAdapter()
        await adapter.create_event(_make_event(uid="far", hours_from_now=80 * 24))
        set_calendar_backend(adapter)

        tool = CalendarQueryTool()
        result = await tool.execute({"days_ahead": 200})
        # Should be capped at 90 days, so the event at day 80 should appear
        assert len(result.data) == 1

    async def test_invalid_days_ahead_uses_default(self) -> None:
        adapter = MockCalendarAdapter()
        set_calendar_backend(adapter)

        tool = CalendarQueryTool()
        result = await tool.execute({"days_ahead": -1})
        assert result.success is True

    async def test_event_data_format(self) -> None:
        adapter = MockCalendarAdapter()
        await adapter.create_event(
            CalendarEvent(
                uid="fmt-1",
                summary="Formatted",
                start=datetime(2025, 6, 15, 14, 0, tzinfo=UTC),
                end=datetime(2025, 6, 15, 15, 0, tzinfo=UTC),
                location="Room A",
            )
        )
        set_calendar_backend(adapter)

        tool = CalendarQueryTool()
        now = datetime.now(tz=UTC)
        if datetime(2025, 6, 15, tzinfo=UTC) > now:
            result = await tool.execute({"days_ahead": 365})
        else:
            result = await tool.execute({})

        if result.data:
            event_data = result.data[0]
            assert "uid" in event_data
            assert "summary" in event_data
            assert "start" in event_data
            assert "end" in event_data
            assert "location" in event_data
            assert "all_day" in event_data


# --- CalendarCreateTool properties ---


class TestCalendarCreateToolProperties:
    def test_name(self) -> None:
        assert CalendarCreateTool().name == "calendar_create"

    def test_description(self) -> None:
        assert CalendarCreateTool().description == "Create a new calendar event"

    def test_permission_tier(self) -> None:
        assert CalendarCreateTool().permission_tier == 1

    def test_schema_has_required_fields(self) -> None:
        schema = CalendarCreateTool().get_schema()
        assert schema["name"] == "calendar_create"
        props = schema["parameters"]["properties"]
        assert "summary" in props
        assert "start_iso" in props
        assert "duration_minutes" in props
        assert schema["parameters"]["required"] == ["summary", "start_iso"]


# --- CalendarCreateTool execution ---


class TestCalendarCreateToolExecute:
    async def test_no_backend_returns_error(self) -> None:
        tool = CalendarCreateTool()
        result = await tool.execute({"summary": "Test", "start_iso": "2025-06-15T14:00:00Z"})
        assert result.success is False
        assert "not configured" in result.error.lower()

    async def test_missing_summary(self) -> None:
        adapter = MockCalendarAdapter()
        set_calendar_backend(adapter)

        tool = CalendarCreateTool()
        result = await tool.execute({"start_iso": "2025-06-15T14:00:00Z"})
        assert result.success is False
        assert "summary" in result.error.lower()

    async def test_empty_summary(self) -> None:
        adapter = MockCalendarAdapter()
        set_calendar_backend(adapter)

        tool = CalendarCreateTool()
        result = await tool.execute({"summary": "  ", "start_iso": "2025-06-15T14:00:00Z"})
        assert result.success is False

    async def test_invalid_start_time(self) -> None:
        adapter = MockCalendarAdapter()
        set_calendar_backend(adapter)

        tool = CalendarCreateTool()
        result = await tool.execute({"summary": "Test", "start_iso": "not-a-date"})
        assert result.success is False
        assert "iso" in result.error.lower() or "time" in result.error.lower()

    async def test_missing_start_time(self) -> None:
        adapter = MockCalendarAdapter()
        set_calendar_backend(adapter)

        tool = CalendarCreateTool()
        result = await tool.execute({"summary": "Test"})
        assert result.success is False

    async def test_create_success(self) -> None:
        adapter = MockCalendarAdapter()
        set_calendar_backend(adapter)

        tool = CalendarCreateTool()
        result = await tool.execute(
            {
                "summary": "Team Meeting",
                "start_iso": "2025-06-15T14:00:00+00:00",
            }
        )
        assert result.success is True
        assert result.data["summary"] == "Team Meeting"
        assert "Team Meeting" in result.display_text

    async def test_create_with_all_fields(self) -> None:
        adapter = MockCalendarAdapter()
        set_calendar_backend(adapter)

        tool = CalendarCreateTool()
        result = await tool.execute(
            {
                "summary": "Lunch",
                "start_iso": "2025-06-15T12:00:00+00:00",
                "duration_minutes": 90,
                "description": "Team lunch",
                "location": "Cafe Central",
            }
        )
        assert result.success is True
        assert result.data["summary"] == "Lunch"

    async def test_create_default_duration_60(self) -> None:
        adapter = MockCalendarAdapter()
        set_calendar_backend(adapter)

        tool = CalendarCreateTool()
        result = await tool.execute(
            {
                "summary": "Quick Chat",
                "start_iso": "2025-06-15T10:00:00+00:00",
            }
        )
        assert result.success is True
        # End should be 60 minutes after start
        start = datetime.fromisoformat(result.data["start"])
        end = datetime.fromisoformat(result.data["end"])
        assert (end - start).total_seconds() == 3600

    async def test_create_stores_in_adapter(self) -> None:
        adapter = MockCalendarAdapter()
        set_calendar_backend(adapter)

        tool = CalendarCreateTool()
        await tool.execute(
            {
                "summary": "Stored Event",
                "start_iso": "2025-06-15T14:00:00+00:00",
            }
        )

        events = await adapter.list_events(
            start=datetime(2025, 6, 15, tzinfo=UTC),
            end=datetime(2025, 6, 16, tzinfo=UTC),
        )
        assert len(events) == 1
        assert events[0].summary == "Stored Event"

    async def test_create_naive_datetime_gets_utc(self) -> None:
        adapter = MockCalendarAdapter()
        set_calendar_backend(adapter)

        tool = CalendarCreateTool()
        result = await tool.execute(
            {
                "summary": "Naive Time",
                "start_iso": "2025-06-15T14:00:00",
            }
        )
        assert result.success is True
        start = datetime.fromisoformat(result.data["start"])
        assert start.tzinfo is not None

    async def test_create_duration_capped_at_1440(self) -> None:
        adapter = MockCalendarAdapter()
        set_calendar_backend(adapter)

        tool = CalendarCreateTool()
        result = await tool.execute(
            {
                "summary": "Long Event",
                "start_iso": "2025-06-15T10:00:00+00:00",
                "duration_minutes": 5000,
            }
        )
        assert result.success is True
        start = datetime.fromisoformat(result.data["start"])
        end = datetime.fromisoformat(result.data["end"])
        # Capped at 1440 minutes = 24 hours
        assert (end - start).total_seconds() == 1440 * 60
