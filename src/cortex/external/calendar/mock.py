"""Mock calendar adapter — in-memory event store for testing and offline use."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from cortex.external.types import CalendarEvent

logger = logging.getLogger(__name__)


class MockCalendarAdapter:
    """In-memory calendar adapter for testing and development.

    Stores events in a list. No real CalDAV server required.
    Satisfies ExternalServiceAdapter protocol.
    """

    def __init__(self) -> None:
        self._events: list[CalendarEvent] = []
        self._connected = False

    async def connect(self) -> None:
        self._connected = True
        logger.info("MockCalendarAdapter connected")

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("MockCalendarAdapter disconnected")

    async def health_check(self) -> bool:
        return self._connected

    @property
    def service_type(self) -> str:
        return "calendar"

    # Calendar-specific methods

    async def list_events(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 20,
    ) -> list[CalendarEvent]:
        """List events within a date range.

        Defaults to now → 7 days ahead.
        """
        now = datetime.now(tz=UTC)
        if start is None:
            start = now
        if end is None:
            end = now + timedelta(days=7)

        matching = [e for e in self._events if e.start >= start and e.start <= end]
        matching.sort(key=lambda e: e.start)
        return matching[:limit]

    async def create_event(self, event: CalendarEvent) -> CalendarEvent:
        """Add an event to the store. Returns the event."""
        self._events.append(event)
        logger.info("MockCalendarAdapter created event: %s", event.summary)
        return event

    async def delete_event(self, uid: str) -> bool:
        """Delete an event by UID. Returns True if found and deleted."""
        before = len(self._events)
        self._events = [e for e in self._events if e.uid != uid]
        deleted = len(self._events) < before
        if deleted:
            logger.info("MockCalendarAdapter deleted event: %s", uid)
        return deleted

    def add_sample_events(self) -> None:
        """Populate with sample events for development/testing."""
        now = datetime.now(tz=UTC)
        samples = [
            CalendarEvent(
                uid="mock-1",
                summary="Team standup",
                start=now + timedelta(hours=1),
                end=now + timedelta(hours=1, minutes=30),
                description="Daily sync meeting",
            ),
            CalendarEvent(
                uid="mock-2",
                summary="Lunch with Sarah",
                start=now + timedelta(hours=4),
                end=now + timedelta(hours=5),
                location="Cafe on Main",
            ),
            CalendarEvent(
                uid="mock-3",
                summary="Project deadline",
                start=now + timedelta(days=2),
                end=now + timedelta(days=2),
                all_day=True,
            ),
        ]
        self._events.extend(samples)
