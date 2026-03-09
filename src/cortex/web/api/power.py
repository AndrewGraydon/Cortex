"""Power management API — battery state and profile control."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/power", tags=["power"])


@router.get("")
async def get_power_state(request: Request) -> dict[str, Any]:
    """Get current power state and profile."""
    services = request.app.state.services
    power_service = services.get("power_service")
    power_manager = services.get("power_manager")

    result: dict[str, Any] = {"available": False}

    if power_service is not None:
        state = await power_service.get_state()
        result.update(
            {
                "available": True,
                "profile": state.profile.value,
                "battery_percent": state.battery_percent,
                "is_charging": state.is_charging,
                "voltage": state.voltage,
            }
        )

    if power_manager is not None:
        result["auto_switch"] = power_manager.auto_switch
        result["is_overridden"] = power_manager.is_overridden
        result["settings"] = power_manager.get_settings()

    return result


@router.post("/override")
async def set_power_override(request: Request) -> dict[str, Any]:
    """Manually override the power profile."""
    services = request.app.state.services
    power_manager = services.get("power_manager")

    if power_manager is None:
        return {"error": "Power manager not configured", "status": "error"}

    body = await request.json()
    profile_str = body.get("profile")
    if profile_str == "auto":
        settings = power_manager.clear_override()
        return {"status": "override_cleared", "settings": settings}

    from cortex.hal.power.types import PowerProfile

    try:
        profile = PowerProfile(profile_str)
    except ValueError:
        return {"error": f"Invalid profile: {profile_str}", "status": "error"}

    settings = power_manager.set_override(profile)
    return {"status": "override_set", "profile": profile.value, "settings": settings}
