"""CalDAV calendar adapter — real CalDAV server integration.

Wraps the `caldav` library to provide calendar operations against
a CalDAV server (Radicale, Nextcloud, Google, etc.).
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from cortex.external.types import CalendarEvent

logger = structlog.get_logger()


class CalDAVCalendarAdapter:
    """CalDAV adapter implementing ExternalServiceAdapter protocol.

    Connects to a CalDAV server using URL + credentials.
    Password is read from the CALDAV_PASSWORD environment variable.
    """

    def __init__(self, url: str, username: str = "") -> None:
        self._url = url
        self._username = username
        self._client: Any = None
        self._calendar: Any = None
        self._connected = False

    async def connect(self) -> None:
        """Connect to the CalDAV server and select the first calendar."""
        try:
            import caldav  # noqa: PLC0415

            password = os.environ.get("CALDAV_PASSWORD", "")
            self._client = caldav.DAVClient(  # type: ignore[operator]
                url=self._url,
                username=self._username,
                password=password,
            )
            principal = self._client.principal()
            calendars = principal.calendars()
            if calendars:
                self._calendar = calendars[0]
                logger.info(
                    "CalDAV connected",
                    url=self._url,
                    calendar=str(self._calendar),
                    calendar_count=len(calendars),
                )
            else:
                logger.warning("CalDAV connected but no calendars found", url=self._url)
            self._connected = True
        except Exception:
            self._connected = False
            logger.exception("CalDAV connection failed", url=self._url)
            raise

    async def disconnect(self) -> None:
        """Disconnect from the CalDAV server."""
        self._client = None
        self._calendar = None
        self._connected = False
        logger.info("CalDAV disconnected")

    async def health_check(self) -> bool:
        """Check if we can reach the CalDAV server."""
        if not self._connected or self._client is None:
            return False
        try:
            self._client.principal()
            return True
        except Exception:
            logger.exception("CalDAV health check failed")
            return False

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
        """List events within a date range from the CalDAV server."""
        if self._calendar is None:
            return []

        now = datetime.now(tz=UTC)
        if start is None:
            start = now
        if end is None:
            end = now + timedelta(days=7)

        try:
            raw_events = self._calendar.date_search(start=start, end=end, expand=True)
            events: list[CalendarEvent] = []
            for raw in raw_events[:limit]:
                event = _parse_vevent(raw)
                if event is not None:
                    events.append(event)
            events.sort(key=lambda e: e.start)
            return events
        except Exception:
            logger.exception("CalDAV list_events failed")
            return []

    async def create_event(self, event: CalendarEvent) -> CalendarEvent:
        """Create an event on the CalDAV server."""
        if self._calendar is None:
            msg = "Not connected to a calendar"
            raise RuntimeError(msg)

        vcal = _build_vcalendar(event)
        try:
            self._calendar.save_event(vcal)
            logger.info("CalDAV event created", summary=event.summary, uid=event.uid)
            return event
        except Exception:
            logger.exception("CalDAV create_event failed", summary=event.summary)
            raise

    async def get_event(self, uid: str) -> CalendarEvent | None:
        """Get a single event by UID from the CalDAV server."""
        if self._calendar is None:
            return None
        try:
            raw_events = self._calendar.events()
            for raw in raw_events:
                vevent = raw.vobject_instance.vevent
                if str(vevent.uid.value) == uid:
                    return _parse_vevent(raw)
            return None
        except Exception:
            logger.exception("CalDAV get_event failed", uid=uid)
            return None

    async def update_event(self, event: CalendarEvent) -> CalendarEvent | None:
        """Update an existing event on the CalDAV server.

        Finds the event by UID, replaces it with the new data.
        Returns the updated event, or None if not found.
        """
        if self._calendar is None:
            return None
        try:
            raw_events = self._calendar.events()
            for raw in raw_events:
                vevent = raw.vobject_instance.vevent
                if str(vevent.uid.value) == event.uid:
                    raw.delete()
                    vcal = _build_vcalendar(event)
                    self._calendar.save_event(vcal)
                    logger.info(
                        "CalDAV event updated",
                        summary=event.summary,
                        uid=event.uid,
                    )
                    return event
            return None
        except Exception:
            logger.exception("CalDAV update_event failed", uid=event.uid)
            return None

    async def delete_event(self, uid: str) -> bool:
        """Delete an event by UID from the CalDAV server."""
        if self._calendar is None:
            return False
        try:
            raw_events = self._calendar.events()
            for raw in raw_events:
                vevent = raw.vobject_instance.vevent
                if str(vevent.uid.value) == uid:
                    raw.delete()
                    logger.info("CalDAV event deleted", uid=uid)
                    return True
            return False
        except Exception:
            logger.exception("CalDAV delete_event failed", uid=uid)
            return False


def _parse_vevent(raw_event: Any) -> CalendarEvent | None:
    """Parse a caldav event object into a CalendarEvent."""
    try:
        vevent = raw_event.vobject_instance.vevent
        uid = str(vevent.uid.value) if hasattr(vevent, "uid") else uuid.uuid4().hex
        summary = str(vevent.summary.value) if hasattr(vevent, "summary") else "Untitled"
        dtstart = vevent.dtstart.value
        dtend = vevent.dtend.value if hasattr(vevent, "dtend") else dtstart

        # Determine if all-day (date vs datetime)
        all_day = not isinstance(dtstart, datetime)

        # Normalize to datetime with timezone
        if all_day:
            start = datetime.combine(dtstart, datetime.min.time(), tzinfo=UTC)
            if not isinstance(dtend, datetime):
                end = datetime.combine(dtend, datetime.min.time(), tzinfo=UTC)
            else:
                end = dtend if dtend.tzinfo else dtend.replace(tzinfo=UTC)
        else:
            start = dtstart if dtstart.tzinfo else dtstart.replace(tzinfo=UTC)
            end = dtend if dtend.tzinfo else dtend.replace(tzinfo=UTC)

        description = ""
        if hasattr(vevent, "description"):
            description = str(vevent.description.value)

        location = ""
        if hasattr(vevent, "location"):
            location = str(vevent.location.value)

        return CalendarEvent(
            uid=uid,
            summary=summary,
            start=start,
            end=end,
            description=description,
            location=location,
            all_day=all_day,
        )
    except Exception:
        logger.exception("Failed to parse CalDAV event")
        return None


def _build_vcalendar(event: CalendarEvent) -> str:
    """Build a VCALENDAR string from a CalendarEvent."""
    uid = event.uid or uuid.uuid4().hex
    dtstart = event.start.strftime("%Y%m%dT%H%M%SZ")
    dtend = event.end.strftime("%Y%m%dT%H%M%SZ")

    if event.all_day:
        dtstart = event.start.strftime("%Y%m%d")
        dtend = event.end.strftime("%Y%m%d")
        dtstart_line = f"DTSTART;VALUE=DATE:{dtstart}"
        dtend_line = f"DTEND;VALUE=DATE:{dtend}"
    else:
        dtstart_line = f"DTSTART:{dtstart}"
        dtend_line = f"DTEND:{dtend}"

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Cortex//CalDAV//EN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        dtstart_line,
        dtend_line,
        f"SUMMARY:{event.summary}",
    ]
    if event.description:
        lines.append(f"DESCRIPTION:{event.description}")
    if event.location:
        lines.append(f"LOCATION:{event.location}")
    lines.extend(["END:VEVENT", "END:VCALENDAR"])
    return "\n".join(lines)
