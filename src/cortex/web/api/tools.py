"""Tool manager API — browse, search, and manage tools via web UI."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tools"])


@router.get("/tools", response_class=HTMLResponse)
async def tools_page(request: Request) -> Any:
    """Render the tool manager page."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "tools.html",
        {"title": "Tools — Cortex"},
    )


@router.get("/api/tools")
async def list_tools(request: Request) -> dict[str, Any]:
    """Return all registered tools."""
    services = request.app.state.services
    registry = services.get("tool_registry")

    if registry is None:
        return {"tools": []}

    tools: list[dict[str, Any]] = []
    for name in registry.tool_names:
        tool = registry.get(name)
        if tool is None:
            continue
        tool_info: dict[str, Any] = {
            "name": tool.name,
            "description": tool.description,
            "tier": tool.permission_tier,
        }
        # Script tools have extra metadata
        if hasattr(tool, "triggers"):
            tool_info["type"] = "script"
            tool_info["triggers"] = tool.triggers
            tool_info["keywords"] = tool.keywords
            tool_info["enabled"] = tool.enabled
        else:
            tool_info["type"] = "python"
            tool_info["enabled"] = True

        tools.append(tool_info)

    return {"tools": tools}


@router.post("/api/tools/reload")
async def reload_tools(request: Request) -> dict[str, Any]:
    """Trigger tool rediscovery (hot-reload)."""
    services = request.app.state.services
    registry = services.get("tool_registry")
    tools_dir = services.get("tools_dir")

    if registry is None or tools_dir is None:
        return {"reloaded": 0, "message": "Tool registry or directory not configured"}

    from cortex.agent.tools.discovery import discover_script_tools

    new_tools = discover_script_tools(tools_dir)
    for tool in new_tools:
        registry.register(tool)

    return {"reloaded": len(new_tools), "total": len(registry)}
