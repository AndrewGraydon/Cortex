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


@router.get("/api/dashboard/services")
async def dashboard_services(request: Request) -> dict[str, Any]:
    """Return external services status for dashboard display."""
    services = request.app.state.services
    ext_manager = services.get("external_service_manager")

    result: dict[str, Any] = {"services": [], "configured": False}

    if ext_manager is None:
        return result

    result["configured"] = True
    health = await ext_manager.health_check_all()
    for name, status in health.items():
        result["services"].append(
            {
                "name": name,
                "status": status.value,
                "healthy": status.value in ("connected", "healthy"),
            }
        )

    # MCP servers
    mcp_client = services.get("mcp_client")
    if mcp_client is not None:
        for name in mcp_client.connected_servers:
            healthy = await mcp_client.health_check(name)
            result["services"].append(
                {
                    "name": f"mcp:{name}",
                    "status": "connected" if healthy else "error",
                    "healthy": healthy,
                }
            )

    # A2A
    a2a_card = services.get("agent_card")
    if a2a_card is not None:
        result["services"].append(
            {
                "name": "a2a",
                "status": "configured",
                "healthy": True,
            }
        )

    return result


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
