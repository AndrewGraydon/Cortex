"""Calendar tools — query and create events. Tier 0 (query) / Tier 1 (create).

Wired to a calendar adapter backend. Falls back to stub responses
if no backend is configured.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from cortex.agent.types import ToolResult
from cortex.external.types import CalendarEvent

logger = logging.getLogger(__name__)

# Module-level backend — set via set_calendar_backend()
_adapter: Any = None


def set_calendar_backend(adapter: Any) -> None:
    """Wire the calendar tools to a real or mock adapter."""
    global _adapter  # noqa: PLW0603
    _adapter = adapter


def get_calendar_backend() -> Any:
    """Get the current calendar backend (for testing)."""
    return _adapter


class CalendarQueryTool:
    """Query upcoming calendar events. Tier 0 (safe, read-only)."""

    @property
    def name(self) -> str:
        return "calendar_query"

    @property
    def description(self) -> str:
        return "List upcoming calendar events"

    @property
    def permission_tier(self) -> int:
        return 0

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "calendar_query",
            "description": "List upcoming calendar events",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": "Number of days ahead to search (default 7)",
                    },
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if _adapter is None:
            return ToolResult(
                tool_name="calendar_query",
                success=True,
                data=[],
                display_text="Calendar is not configured.",
            )

        days = arguments.get("days_ahead", 7)
        if not isinstance(days, int) or days < 1:
            days = 7
        days = min(days, 90)  # cap at 90 days

        try:
            now = datetime.now(tz=UTC)
            events = await _adapter.list_events(
                start=now,
                end=now + timedelta(days=days),
            )

            if not events:
                return ToolResult(
                    tool_name="calendar_query",
                    success=True,
                    data=[],
                    display_text=f"No events in the next {days} days.",
                )

            data = [
                {
                    "uid": e.uid,
                    "summary": e.summary,
                    "start": e.start.isoformat(),
                    "end": e.end.isoformat(),
                    "location": e.location,
                    "all_day": e.all_day,
                }
                for e in events
            ]

            # Build display text for TTS
            if len(events) == 1:
                display = f"You have 1 event: {events[0].format_display()}."
            else:
                items = [e.format_display() for e in events[:5]]
                display = f"You have {len(events)} events. " + ". ".join(items) + "."

            return ToolResult(
                tool_name="calendar_query",
                success=True,
                data=data,
                display_text=display,
            )
        except Exception as e:
            logger.exception("Calendar query failed")
            return ToolResult(
                tool_name="calendar_query",
                success=False,
                error=str(e),
            )


class CalendarCreateTool:
    """Create a calendar event. Tier 1 (normal, logged)."""

    @property
    def name(self) -> str:
        return "calendar_create"

    @property
    def description(self) -> str:
        return "Create a new calendar event"

    @property
    def permission_tier(self) -> int:
        return 1

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "calendar_create",
            "description": "Create a new calendar event",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Event title",
                    },
                    "start_iso": {
                        "type": "string",
                        "description": "Start time in ISO 8601 format",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Duration in minutes (default 60)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Event description (optional)",
                    },
                    "location": {
                        "type": "string",
                        "description": "Event location (optional)",
                    },
                },
                "required": ["summary", "start_iso"],
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if _adapter is None:
            return ToolResult(
                tool_name="calendar_create",
                success=False,
                error="Calendar is not configured.",
            )

        summary = arguments.get("summary", "").strip()
        if not summary:
            return ToolResult(
                tool_name="calendar_create",
                success=False,
                error="Event summary is required.",
            )

        start_iso = arguments.get("start_iso", "")
        try:
            start = datetime.fromisoformat(start_iso)
            if start.tzinfo is None:
                start = start.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            return ToolResult(
                tool_name="calendar_create",
                success=False,
                error="Invalid start time. Use ISO 8601 format.",
            )

        duration = arguments.get("duration_minutes", 60)
        if not isinstance(duration, int) or duration < 1:
            duration = 60
        duration = min(duration, 1440)  # cap at 24 hours

        end = start + timedelta(minutes=duration)

        event = CalendarEvent(
            uid=uuid.uuid4().hex,
            summary=summary,
            start=start,
            end=end,
            description=arguments.get("description", ""),
            location=arguments.get("location", ""),
        )

        try:
            created = await _adapter.create_event(event)
            return ToolResult(
                tool_name="calendar_create",
                success=True,
                data={
                    "uid": created.uid,
                    "summary": created.summary,
                    "start": created.start.isoformat(),
                    "end": created.end.isoformat(),
                },
                display_text=f"Created event: {created.format_display()}.",
            )
        except Exception as e:
            logger.exception("Calendar create failed")
            return ToolResult(
                tool_name="calendar_create",
                success=False,
                error=str(e),
            )
