"""Tool pipeline API — create, review, approve, deploy, and promote tools."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from cortex.agent.tools.pipeline.code_generator import generate_code
from cortex.agent.tools.pipeline.reviewer import review_tool
from cortex.agent.tools.pipeline.spec_generator import generate_spec
from cortex.agent.tools.pipeline.types import PipelineStage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pipeline", tags=["tool-pipeline"])


@router.post("/create")
async def create_tool(request: Request) -> dict[str, Any]:
    """Create a new tool from a specification.

    Body JSON: {name, description, parameters?, keywords?, triggers?, timeout_seconds?}
    """
    body = await request.json()
    name = body.get("name", "")
    description = body.get("description", "")

    if not name or not description:
        return {"error": "name and description are required", "status": "error"}

    try:
        spec = generate_spec(
            name=name,
            description=description,
            parameters=body.get("parameters"),
            keywords=body.get("keywords"),
            triggers=body.get("triggers"),
            timeout_seconds=body.get("timeout_seconds", 10.0),
        )
    except ValueError as e:
        return {"error": str(e), "status": "error"}

    draft = generate_code(spec)

    # Store draft in service container
    services = request.app.state.services
    drafts = services.get("tool_drafts")
    if drafts is None:
        drafts = {}
        services.set("tool_drafts", drafts)
    drafts[name] = draft

    # Add to catalog if available
    catalog = services.get("tool_catalog")
    if catalog is not None:
        await catalog.add(
            name=name,
            description=description,
            source="user",
            stage=PipelineStage.DRAFT,
        )

    return {
        "status": "created",
        "name": name,
        "stage": draft.stage.value,
        "manifest_yaml": draft.manifest_yaml,
        "script_code": draft.script_code,
    }


@router.get("/drafts")
async def list_drafts(request: Request) -> dict[str, Any]:
    """List all tool drafts."""
    services = request.app.state.services
    drafts = services.get("tool_drafts") or {}

    return {
        "drafts": [
            {
                "name": draft.spec.name,
                "description": draft.spec.description,
                "stage": draft.stage.value,
                "has_review": draft.review_result is not None,
            }
            for draft in drafts.values()
        ]
    }


@router.post("/{name}/review")
async def review_draft(name: str, request: Request) -> dict[str, Any]:
    """Run automated review on a tool draft."""
    services = request.app.state.services
    drafts = services.get("tool_drafts") or {}

    draft = drafts.get(name)
    if draft is None:
        return {"error": f"Draft '{name}' not found", "status": "error"}

    result = review_tool(draft)

    return {
        "status": "reviewed",
        "name": name,
        "passed": result.passed,
        "issues": result.issues,
        "stage": draft.stage.value,
    }


@router.post("/{name}/approve")
async def approve_tool(name: str, request: Request) -> dict[str, Any]:
    """Approve a reviewed tool for deployment."""
    services = request.app.state.services
    drafts = services.get("tool_drafts") or {}

    draft = drafts.get(name)
    if draft is None:
        return {"error": f"Draft '{name}' not found", "status": "error"}

    if draft.review_result is None or not draft.review_result.passed:
        return {
            "error": "Tool must pass review before approval",
            "status": "error",
        }

    draft.stage = PipelineStage.APPROVED

    # Update catalog
    catalog = services.get("tool_catalog")
    if catalog is not None:
        await catalog.update_stage(name, PipelineStage.APPROVED)

    return {"status": "approved", "name": name, "stage": draft.stage.value}


@router.post("/{name}/deploy")
async def deploy_tool(name: str, request: Request) -> dict[str, Any]:
    """Deploy an approved tool to the filesystem."""
    services = request.app.state.services
    drafts = services.get("tool_drafts") or {}
    deployer = services.get("tool_deployer")

    draft = drafts.get(name)
    if draft is None:
        return {"error": f"Draft '{name}' not found", "status": "error"}

    if deployer is None:
        return {"error": "Tool deployer not configured", "status": "error"}

    try:
        tool_dir = deployer.deploy(draft)
    except ValueError as e:
        return {"error": str(e), "status": "error"}

    # Update catalog
    catalog = services.get("tool_catalog")
    if catalog is not None:
        await catalog.update_stage(name, PipelineStage.DEPLOYED)

    return {
        "status": "deployed",
        "name": name,
        "path": str(tool_dir),
        "stage": draft.stage.value,
    }


@router.post("/{name}/promote")
async def promote_tool(name: str, request: Request) -> dict[str, Any]:
    """Promote a tool to a lower permission tier."""
    services = request.app.state.services
    tracker = services.get("promotion_tracker")

    if tracker is None:
        return {"error": "Promotion tracker not configured", "status": "error"}

    promoted = await tracker.promote(name)
    if not promoted:
        return {"error": f"Tool '{name}' is not eligible for promotion", "status": "error"}

    return {"status": "promoted", "name": name}


@router.post("/{name}/disable")
async def disable_tool(name: str, request: Request) -> dict[str, Any]:
    """Disable a deployed tool."""
    services = request.app.state.services
    registry = services.get("tool_registry")

    if registry is None:
        return {"error": "Tool registry not configured", "status": "error"}

    tool = registry.get(name)
    if tool is None:
        return {"error": f"Tool '{name}' not found in registry", "status": "error"}

    if hasattr(tool, "enabled"):
        tool.enabled = False

    # Update catalog
    catalog = services.get("tool_catalog")
    if catalog is not None:
        await catalog.update_stage(name, PipelineStage.DISABLED)

    return {"status": "disabled", "name": name}


@router.get("/catalog")
async def get_catalog(request: Request) -> dict[str, Any]:
    """List all tools in the catalog."""
    services = request.app.state.services
    catalog = services.get("tool_catalog")

    if catalog is None:
        return {"tools": []}

    source = request.query_params.get("source")
    stage_str = request.query_params.get("stage")
    stage = PipelineStage(stage_str) if stage_str else None

    tools = await catalog.list_all(source=source, stage=stage)
    return {"tools": tools}
