"""Dashboard API — page and HTMX partial endpoints.

Provides real-time system health, active timers, and recent actions.
HTMX polls the partial endpoints for live updates.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> Any:
    """Render the dashboard page."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"title": "Dashboard — Cortex"},
    )


@router.get("/api/dashboard/health")
async def dashboard_health(request: Request) -> dict[str, Any]:
    """Return health data for dashboard cards."""
    services = request.app.state.services
    monitor = services.health_monitor

    health = await monitor.check()
    result: dict[str, Any] = health.to_dict()
    return result


@router.get("/api/dashboard/timers")
async def dashboard_timers(request: Request) -> dict[str, Any]:
    """Return active timers for dashboard display."""
    services = request.app.state.services
    scheduler = services.get("scheduler")

    if scheduler is None:
        return {"timers": []}

    timers = await scheduler.get_active_timers()
    now = time.time()
    return {
        "timers": [
            {
                "id": t.id,
                "label": t.label,
                "remaining_seconds": max(0, t.fire_at - now),
                "created_at": t.created_at,
            }
            for t in timers
        ]
    }


@router.get("/api/dashboard/recent")
async def dashboard_recent(request: Request) -> dict[str, Any]:
    """Return recent actions for dashboard display."""
    services = request.app.state.services
    audit = services.get("audit")

    if audit is None:
        return {"actions": []}

    entries = await audit.query(limit=20)
    return {
        "actions": [
            {
                "id": e.id,
                "timestamp": e.timestamp,
                "action_type": e.action_type,
                "action_id": e.action_id,
                "result": e.result,
                "source": e.source,
                "duration_ms": round(e.duration_ms, 1),
            }
            for e in entries
        ]
    }
