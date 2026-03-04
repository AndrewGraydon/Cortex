"""Security console API — audit log viewer and permission management."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["security"])


@router.get("/security", response_class=HTMLResponse)
async def security_page(request: Request) -> Any:
    """Render the security console page."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "security.html",
        {"title": "Security — Cortex"},
    )


@router.get("/api/security/audit")
async def get_audit_log(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    action_type: str | None = None,
) -> dict[str, Any]:
    """Return paginated audit log entries."""
    services = request.app.state.services
    audit_log = services.get("audit_log")

    if audit_log is None:
        return {"entries": [], "total": 0, "limit": limit, "offset": offset}

    entries = await audit_log.query(
        action_type=action_type,
        limit=limit,
        offset=offset,
    )
    total = await audit_log.count()

    return {
        "entries": [
            {
                "id": e.id,
                "timestamp": e.timestamp,
                "action_type": e.action_type,
                "action_id": e.action_id,
                "permission_tier": e.permission_tier,
                "approval_status": e.approval_status,
                "result": e.result,
                "source": e.source,
                "duration_ms": round(e.duration_ms, 1),
                "error_message": e.error_message,
            }
            for e in entries
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/api/security/permissions")
async def get_permissions(request: Request) -> dict[str, Any]:
    """Return current permission tier descriptions."""
    return {
        "tiers": [
            {"tier": 0, "name": "Info", "description": "Read-only, no side effects"},
            {"tier": 1, "name": "Low", "description": "Reversible actions"},
            {"tier": 2, "name": "Medium", "description": "Requires approval"},
            {"tier": 3, "name": "Danger", "description": "Destructive, always blocked"},
        ],
    }
