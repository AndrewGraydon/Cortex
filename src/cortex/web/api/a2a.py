"""A2A protocol web routes — Agent Card and JSON-RPC task endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["a2a"])


@router.get("/.well-known/agent.json")
async def agent_card(request: Request) -> JSONResponse:
    """Serve the A2A Agent Card (unauthenticated per A2A spec)."""
    services = request.app.state.services
    card = services.get("agent_card")

    if card is None:
        return JSONResponse(
            content={"error": "A2A not configured"},
            status_code=503,
        )

    return JSONResponse(content=card.to_dict())


@router.post("/a2a")
async def a2a_endpoint(request: Request) -> JSONResponse:
    """Handle A2A JSON-RPC requests."""
    services = request.app.state.services
    a2a_server = services.get("a2a_server")

    if a2a_server is None:
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": "A2A server not configured"},
            },
        )

    try:
        data = await request.json()
    except Exception:
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            },
        )

    result = await a2a_server.handle_request(data)
    return JSONResponse(content=result)
