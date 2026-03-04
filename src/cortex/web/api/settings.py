"""Settings API — view and browse configuration via web UI."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> Any:
    """Render the settings page."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"title": "Settings — Cortex"},
    )


@router.get("/api/settings")
async def get_all_settings(request: Request) -> dict[str, Any]:
    """Return all configuration sections (read-only)."""
    config = request.app.state.config
    return {"settings": config.model_dump()}


@router.get("/api/settings/{section}")
async def get_settings_section(
    request: Request,
    section: str,
) -> dict[str, Any]:
    """Return a specific configuration section."""
    config = request.app.state.config
    if not hasattr(config, section):
        return {"error": f"Unknown section: {section}", "section": section}
    section_data = getattr(config, section)
    if hasattr(section_data, "model_dump"):
        return {"section": section, "data": section_data.model_dump()}
    return {"section": section, "data": section_data}
