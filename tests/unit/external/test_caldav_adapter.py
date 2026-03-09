"""Tests for CalDAV calendar adapters (mock and real)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cortex.external.calendar.mock import MockCalendarAdapter
from cortex.external.protocols import ExternalServiceAdapter
from cortex.external.types import CalendarEvent

# --- Helpers ---


def _make_event(
    uid: str = "test-1",
    summary: str = "Test Event",
    hours_from_now: float = 1,
    duration_hours: float = 1,
    **kwargs: object,
) -> CalendarEvent:
    now = datetime.now(tz=UTC)
    return CalendarEvent(
        uid=uid,
        summary=summary,
        start=now + timedelta(hours=hours_from_now),
        end=now + timedelta(hours=hours_from_now + duration_hours),
        **kwargs,  # type: ignore[arg-type]
    )


# --- MockCalendarAdapter Protocol Compliance ---


class TestMockAdapterProtocol:
    def test_satisfies_external_service_adapter(self) -> None:
        adapter = MockCalendarAdapter()
        assert isinstance(adapter, ExternalServiceAdapter)

    def test_service_type(self) -> None:
        adapter = MockCalendarAdapter()
        assert adapter.service_type == "calendar"


# --- MockCalendarAdapter Lifecycle ---


class TestMockAdapterLifecycle:
    async def test_connect(self) -> None:
        adapter = MockCalendarAdapter()
        await adapter.connect()
        assert adapter._connected is True

    async def test_disconnect(self) -> None:
        adapter = MockCalendarAdapter()
        await adapter.connect()
        await adapter.disconnect()
        assert adapter._connected is False

    async def test_health_check_connected(self) -> None:
        adapter = MockCalendarAdapter()
        await adapter.connect()
        assert await adapter.health_check() is True

    async def test_health_check_disconnected(self) -> None:
        adapter = MockCalendarAdapter()
        assert await adapter.health_check() is False


# --- MockCalendarAdapter Events ---


class TestMockAdapterListEvents:
    async def test_list_empty(self) -> None:
        adapter = MockCalendarAdapter()
        events = await adapter.list_events()
        assert events == []

    async def test_list_events_returns_matching(self) -> None:
        adapter = MockCalendarAdapter()
        event = _make_event(uid="e1", hours_from_now=1)
        await adapter.create_event(event)

        events = await adapter.list_events()
        assert len(events) == 1
        assert events[0].uid == "e1"

    async def test_list_events_filters_by_date_range(self) -> None:
        adapter = MockCalendarAdapter()
        # Event within range
        await adapter.create_event(_make_event(uid="in-range", hours_from_now=2))
        # Event outside range (30 days out)
        await adapter.create_event(_make_event(uid="out-range", hours_from_now=30 * 24))

        now = datetime.now(tz=UTC)
        events = await adapter.list_events(
            start=now,
            end=now + timedelta(days=7),
        )
        assert len(events) == 1
        assert events[0].uid == "in-range"

    async def test_list_events_sorted_by_start(self) -> None:
        adapter = MockCalendarAdapter()
        await adapter.create_event(_make_event(uid="later", hours_from_now=5))
        await adapter.create_event(_make_event(uid="sooner", hours_from_now=1))
        await adapter.create_event(_make_event(uid="middle", hours_from_now=3))

        events = await adapter.list_events()
        uids = [e.uid for e in events]
        assert uids == ["sooner", "middle", "later"]

    async def test_list_events_respects_limit(self) -> None:
        adapter = MockCalendarAdapter()
        for i in range(10):
            await adapter.create_event(_make_event(uid=f"e{i}", hours_from_now=i + 1))

        events = await adapter.list_events(limit=3)
        assert len(events) == 3

    async def test_list_events_default_range_7_days(self) -> None:
        adapter = MockCalendarAdapter()
        # Event at day 5 (within default range)
        await adapter.create_event(_make_event(uid="day5", hours_from_now=5 * 24))
        # Event at day 10 (outside default range)
        await adapter.create_event(_make_event(uid="day10", hours_from_now=10 * 24))

        events = await adapter.list_events()
        assert len(events) == 1
        assert events[0].uid == "day5"


class TestMockAdapterCreateEvent:
    async def test_create_event(self) -> None:
        adapter = MockCalendarAdapter()
        event = _make_event(uid="new-1", summary="New Event")
        result = await adapter.create_event(event)
        assert result.uid == "new-1"
        assert result.summary == "New Event"

    async def test_created_event_appears_in_list(self) -> None:
        adapter = MockCalendarAdapter()
        event = _make_event(uid="created", hours_from_now=1)
        await adapter.create_event(event)

        events = await adapter.list_events()
        assert len(events) == 1
        assert events[0].uid == "created"


class TestMockAdapterDeleteEvent:
    async def test_delete_existing(self) -> None:
        adapter = MockCalendarAdapter()
        await adapter.create_event(_make_event(uid="to-delete"))

        deleted = await adapter.delete_event("to-delete")
        assert deleted is True

        events = await adapter.list_events()
        assert len(events) == 0

    async def test_delete_nonexistent(self) -> None:
        adapter = MockCalendarAdapter()
        deleted = await adapter.delete_event("nonexistent")
        assert deleted is False

    async def test_delete_only_removes_target(self) -> None:
        adapter = MockCalendarAdapter()
        await adapter.create_event(_make_event(uid="keep"))
        await adapter.create_event(_make_event(uid="remove"))

        await adapter.delete_event("remove")
        events = await adapter.list_events()
        assert len(events) == 1
        assert events[0].uid == "keep"


class TestMockAdapterSampleEvents:
    def test_add_sample_events(self) -> None:
        adapter = MockCalendarAdapter()
        adapter.add_sample_events()
        assert len(adapter._events) == 3

    async def test_sample_events_appear_in_list(self) -> None:
        adapter = MockCalendarAdapter()
        adapter.add_sample_events()
        events = await adapter.list_events(
            start=datetime.now(tz=UTC),
            end=datetime.now(tz=UTC) + timedelta(days=30),
        )
        assert len(events) == 3


# --- CalDAV adapter build/parse helpers ---


class TestCalDAVHelpers:
    def test_build_vcalendar_timed(self) -> None:
        from cortex.external.calendar.caldav_adapter import _build_vcalendar

        event = CalendarEvent(
            uid="test-uid",
            summary="Test Meeting",
            start=datetime(2025, 3, 15, 10, 0, tzinfo=UTC),
            end=datetime(2025, 3, 15, 11, 0, tzinfo=UTC),
        )
        vcal = _build_vcalendar(event)
        assert "BEGIN:VCALENDAR" in vcal
        assert "UID:test-uid" in vcal
        assert "SUMMARY:Test Meeting" in vcal
        assert "DTSTART:20250315T100000Z" in vcal
        assert "DTEND:20250315T110000Z" in vcal
        assert "END:VCALENDAR" in vcal

    def test_build_vcalendar_all_day(self) -> None:
        from cortex.external.calendar.caldav_adapter import _build_vcalendar

        event = CalendarEvent(
            uid="allday-uid",
            summary="All Day Event",
            start=datetime(2025, 3, 15, 0, 0, tzinfo=UTC),
            end=datetime(2025, 3, 16, 0, 0, tzinfo=UTC),
            all_day=True,
        )
        vcal = _build_vcalendar(event)
        assert "DTSTART;VALUE=DATE:20250315" in vcal
        assert "DTEND;VALUE=DATE:20250316" in vcal

    def test_build_vcalendar_with_location_and_description(self) -> None:
        from cortex.external.calendar.caldav_adapter import _build_vcalendar

        event = CalendarEvent(
            uid="loc-uid",
            summary="Lunch",
            start=datetime(2025, 3, 15, 12, 0, tzinfo=UTC),
            end=datetime(2025, 3, 15, 13, 0, tzinfo=UTC),
            location="Cafe Central",
            description="Team lunch",
        )
        vcal = _build_vcalendar(event)
        assert "LOCATION:Cafe Central" in vcal
        assert "DESCRIPTION:Team lunch" in vcal

    def test_build_vcalendar_no_optional_fields(self) -> None:
        from cortex.external.calendar.caldav_adapter import _build_vcalendar

        event = CalendarEvent(
            uid="min-uid",
            summary="Minimal",
            start=datetime(2025, 3, 15, 10, 0, tzinfo=UTC),
            end=datetime(2025, 3, 15, 11, 0, tzinfo=UTC),
        )
        vcal = _build_vcalendar(event)
        assert "LOCATION" not in vcal
        assert "DESCRIPTION" not in vcal
