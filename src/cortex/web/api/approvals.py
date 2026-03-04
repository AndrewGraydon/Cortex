"""Approval flow API — web-based approve/deny for Tier 2-3 actions.

Extends the button-based approval with a web channel. Both button and web
can resolve the same pending request (first response wins).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("/pending")
async def get_pending(request: Request) -> dict[str, Any]:
    """Return the currently pending approval request, if any."""
    services = request.app.state.services
    approval_mgr = services.get("approval_manager")

    if approval_mgr is None or approval_mgr.pending is None:
        return {"pending": None}

    req = approval_mgr.pending
    return {
        "pending": {
            "request_id": req.request_id,
            "action_id": req.action_id,
            "description": req.action_description,
            "tier": req.permission_tier.value,
            "timeout_seconds": req.timeout_seconds,
            "parameters": req.parameters,
        }
    }


@router.post("/{request_id}/approve")
async def approve_request(request_id: str, request: Request) -> JSONResponse:
    """Approve a pending approval request via web."""
    services = request.app.state.services
    approval_mgr = services.get("approval_manager")

    if approval_mgr is None:
        return JSONResponse(
            {"error": "Approval manager not configured"},
            status_code=503,
        )

    pending = approval_mgr.pending
    if pending is None or pending.request_id != request_id:
        return JSONResponse(
            {"error": "No matching pending request"},
            status_code=404,
        )

    # Resolve the pending request as approved via web channel
    web_approver = services.get("web_approver")
    if web_approver:
        await web_approver.resolve(request_id, approved=True)

    logger.info("Web approval: approved request %s", request_id)
    return JSONResponse({"status": "approved", "request_id": request_id})


@router.post("/{request_id}/deny")
async def deny_request(request_id: str, request: Request) -> JSONResponse:
    """Deny a pending approval request via web."""
    services = request.app.state.services
    approval_mgr = services.get("approval_manager")

    if approval_mgr is None:
        return JSONResponse(
            {"error": "Approval manager not configured"},
            status_code=503,
        )

    pending = approval_mgr.pending
    if pending is None or pending.request_id != request_id:
        return JSONResponse(
            {"error": "No matching pending request"},
            status_code=404,
        )

    web_approver = services.get("web_approver")
    if web_approver:
        await web_approver.resolve(request_id, approved=False)

    logger.info("Web approval: denied request %s", request_id)
    return JSONResponse({"status": "denied", "request_id": request_id})


@router.get("/history")
async def approval_history(request: Request) -> dict[str, Any]:
    """Return recent approval history."""
    services = request.app.state.services
    approval_mgr = services.get("approval_manager")

    if approval_mgr is None:
        return {"history": []}

    return {
        "history": [
            {
                "request_id": req.request_id,
                "action_id": req.action_id,
                "description": req.action_description,
                "tier": req.permission_tier.value,
                "result": status.value,
            }
            for req, status in approval_mgr.history
        ]
    }
