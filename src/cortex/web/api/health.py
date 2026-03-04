"""Health API endpoint — wraps existing HealthMonitor."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from cortex.agent.health import HealthMonitor
from cortex.web.dependencies import get_health_monitor

router = APIRouter(prefix="/api", tags=["health"])

HealthMonitorDep = Annotated[HealthMonitor, Depends(get_health_monitor)]


@router.get("/health")
async def health_check(monitor: HealthMonitorDep) -> dict[str, Any]:
    """Return system health as JSON.

    This endpoint is unauthenticated — accessible without login.
    """
    result = await monitor.check()
    return result.to_dict()
