"""Network security API — domain allowlist and firewall rules."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/security/network", tags=["network-security"])


@router.get("")
async def get_network_rules(request: Request) -> dict[str, Any]:
    """Get current network security rules."""
    services = request.app.state.services
    net_security = services.get("network_security")

    if net_security is None:
        return {"enabled": False, "message": "Network security not configured"}

    result: dict[str, Any] = net_security.get_rules()
    return result


@router.post("/allowlist")
async def add_to_allowlist(request: Request) -> dict[str, Any]:
    """Add a domain to the allowlist."""
    services = request.app.state.services
    net_security = services.get("network_security")

    if net_security is None:
        return {"error": "Network security not configured", "status": "error"}

    body = await request.json()
    domain = body.get("domain", "")
    if not domain:
        return {"error": "domain is required", "status": "error"}

    net_security.add_to_allowlist(domain)
    return {"status": "added", "domain": domain}


@router.delete("/allowlist")
async def remove_from_allowlist(request: Request) -> dict[str, Any]:
    """Remove a domain from the allowlist."""
    services = request.app.state.services
    net_security = services.get("network_security")

    if net_security is None:
        return {"error": "Network security not configured", "status": "error"}

    body = await request.json()
    domain = body.get("domain", "")
    if not domain:
        return {"error": "domain is required", "status": "error"}

    net_security.remove_from_allowlist(domain)
    return {"status": "removed", "domain": domain}
