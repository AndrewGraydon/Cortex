"""Calendar API routes — page and AJAX endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from cortex.external.types import CalendarEvent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["calendar"])


@router.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request) -> Any:
    """Render the calendar page."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "calendar.html",
        {"title": "Calendar — Cortex"},
    )


@router.get("/api/calendar/events")
async def list_events(
    request: Request,
    days_ahead: int = 7,
) -> dict[str, Any]:
    """List upcoming calendar events as JSON."""
    adapter = _get_calendar_adapter(request)
    if adapter is None:
        return {"events": [], "configured": False}

    days_ahead = max(1, min(days_ahead, 90))
    now = datetime.now(tz=UTC)

    try:
        events = await adapter.list_events(
            start=now,
            end=now + timedelta(days=days_ahead),
        )
        return {
            "events": [_event_to_dict(e) for e in events],
            "configured": True,
            "days_ahead": days_ahead,
        }
    except Exception:
        logger.exception("Failed to list calendar events")
        return {"events": [], "configured": True, "error": "Failed to fetch events"}


@router.post("/api/calendar/events")
async def create_event(request: Request) -> dict[str, Any]:
    """Create a new calendar event."""
    adapter = _get_calendar_adapter(request)
    if adapter is None:
        return {"success": False, "error": "Calendar not configured"}

    body = await request.json()
    summary = body.get("summary", "").strip()
    if not summary:
        return {"success": False, "error": "Event summary is required"}

    start_iso = body.get("start")
    try:
        start = datetime.fromisoformat(start_iso)
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return {"success": False, "error": "Invalid start time"}

    duration_minutes = body.get("duration_minutes", 60)
    end = start + timedelta(minutes=duration_minutes)

    event = CalendarEvent(
        uid=uuid.uuid4().hex,
        summary=summary,
        start=start,
        end=end,
        description=body.get("description", ""),
        location=body.get("location", ""),
        all_day=body.get("all_day", False),
    )

    try:
        created = await adapter.create_event(event)
        return {"success": True, "event": _event_to_dict(created)}
    except Exception:
        logger.exception("Failed to create calendar event")
        return {"success": False, "error": "Failed to create event"}


@router.delete("/api/calendar/events/{uid}")
async def delete_event(request: Request, uid: str) -> dict[str, Any]:
    """Delete a calendar event by UID."""
    adapter = _get_calendar_adapter(request)
    if adapter is None:
        return {"success": False, "error": "Calendar not configured"}

    try:
        deleted = await adapter.delete_event(uid)
        return {"success": deleted}
    except Exception:
        logger.exception("Failed to delete calendar event")
        return {"success": False, "error": "Failed to delete event"}


def _get_calendar_adapter(request: Request) -> Any:
    """Get the calendar adapter from the service container."""
    services = request.app.state.services
    ext_manager = services.get("external_service_manager")
    if ext_manager is None:
        return None
    return ext_manager.get("calendar")


def _event_to_dict(event: CalendarEvent) -> dict[str, Any]:
    """Convert a CalendarEvent to a JSON-serializable dict."""
    return {
        "uid": event.uid,
        "summary": event.summary,
        "start": event.start.isoformat(),
        "end": event.end.isoformat(),
        "description": event.description,
        "location": event.location,
        "all_day": event.all_day,
        "display": event.format_display(),
    }
