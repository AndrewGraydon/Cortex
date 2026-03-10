"""Health monitoring — polls component health and computes overall status.

Provides structured health data for the /api/health endpoint.
Supports reactive callbacks when health state changes.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ComponentHealth:
    """Health status for a single component."""

    name: str
    status: str = "healthy"  # healthy, degraded, unhealthy
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemHealth:
    """Aggregated system health status."""

    status: str  # healthy, degraded, unhealthy
    uptime_seconds: float
    components: list[ComponentHealth]
    models_loaded: list[str]
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict for the health endpoint."""
        return {
            "status": self.status,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "timestamp": self.timestamp,
            "components": {c.name: {"status": c.status, **c.details} for c in self.components},
            "models_loaded": self.models_loaded,
        }

    def component_details(self, name: str) -> dict[str, Any]:
        """Get details dict for a named component."""
        for c in self.components:
            if c.name == name:
                return c.details
        return {}


class HealthMonitor:
    """Monitors system health by polling components.

    Supports reactive polling: call ``start_polling()`` to begin periodic
    health checks with callbacks on state changes.

    Args:
        npu: NPU service for model/temperature status.
        poll_interval_s: Seconds between health polls.
    """

    def __init__(
        self,
        npu: Any = None,
        poll_interval_s: float = 30.0,
    ) -> None:
        self._npu = npu
        self._poll_interval = poll_interval_s
        self._start_time = time.time()
        self._on_change_callbacks: list[Callable[[SystemHealth], None]] = []
        self._last_status: str = "healthy"
        self._poll_task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._start_time

    @property
    def is_polling(self) -> bool:
        return self._running

    def on_health_change(self, callback: Callable[[SystemHealth], None]) -> None:
        """Register a callback invoked when the overall health status changes."""
        self._on_change_callbacks.append(callback)

    async def start_polling(self) -> None:
        """Start periodic health check loop with change detection."""
        if self._running:
            return
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Health polling started (interval=%.1fs)", self._poll_interval)

    async def stop_polling(self) -> None:
        """Stop periodic health check loop."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        logger.info("Health polling stopped")

    async def _poll_loop(self) -> None:
        """Periodic health check loop with change detection."""
        while self._running:
            try:
                health = await self.check()
                if health.status != self._last_status:
                    logger.info(
                        "Health status changed: %s -> %s",
                        self._last_status,
                        health.status,
                    )
                    self._last_status = health.status
                    for cb in self._on_change_callbacks:
                        try:
                            cb(health)
                        except Exception:
                            logger.exception("Health change callback error")
            except Exception:
                logger.exception("Health check failed")
            await asyncio.sleep(self._poll_interval)

    async def check(self) -> SystemHealth:
        """Run a full health check."""
        components: list[ComponentHealth] = []

        # CPU health
        components.append(self._check_cpu())

        # Memory health
        components.append(self._check_memory())

        # Storage health
        components.append(self._check_storage())

        # NPU health
        if self._npu:
            components.append(await self._check_npu(self._npu))

        # Compute overall status
        statuses = [c.status for c in components]
        if "unhealthy" in statuses:
            overall = "unhealthy"
        elif "degraded" in statuses:
            overall = "degraded"
        else:
            overall = "healthy"

        # Models loaded
        models: list[str] = []
        if self._npu and hasattr(self._npu, "get_status"):
            try:
                npu_status = await self._npu.get_status()
                models = npu_status.models_loaded
            except Exception:
                logger.warning("Could not get NPU status for model list")

        return SystemHealth(
            status=overall,
            uptime_seconds=self.uptime_seconds,
            components=components,
            models_loaded=models,
            timestamp=time.time(),
        )

    @staticmethod
    def _check_cpu() -> ComponentHealth:
        """Check CPU health via load average."""
        try:
            load_1m = os.getloadavg()[0]
            cpu_count = os.cpu_count() or 1
            status = "healthy"
            if load_1m > cpu_count * 2:
                status = "unhealthy"
            elif load_1m > cpu_count:
                status = "degraded"
            return ComponentHealth(
                name="cpu",
                status=status,
                details={"load_1m": round(load_1m, 2)},
            )
        except (OSError, AttributeError):
            return ComponentHealth(
                name="cpu",
                status="healthy",
                details={"load_1m": 0.0},
            )

    @staticmethod
    def _check_memory() -> ComponentHealth:
        """Check memory usage."""
        try:
            import shutil

            total, used, free = shutil.disk_usage("/")  # Approximate for RAM
            # Use /proc/meminfo on Linux, fallback to basic check
            used_pct = 0.0
            try:
                with open("/proc/meminfo") as f:
                    lines = f.readlines()
                mem_total = int(lines[0].split()[1])
                mem_available = int(lines[2].split()[1])
                used_pct = (1 - mem_available / mem_total) * 100
            except (FileNotFoundError, IndexError, ValueError):
                used_pct = 30.0  # Default for macOS/non-Linux

            status = "healthy"
            if used_pct > 90:
                status = "unhealthy"
            elif used_pct > 80:
                status = "degraded"
            return ComponentHealth(
                name="memory",
                status=status,
                details={"used_pct": round(used_pct, 1)},
            )
        except Exception:
            return ComponentHealth(name="memory", status="healthy", details={})

    @staticmethod
    def _check_storage() -> ComponentHealth:
        """Check disk storage usage."""
        try:
            import shutil

            total, used, free = shutil.disk_usage("/")
            used_pct = (used / total) * 100
            status = "healthy"
            if used_pct > 95:
                status = "unhealthy"
            elif used_pct > 85:
                status = "degraded"
            return ComponentHealth(
                name="storage",
                status=status,
                details={"used_pct": round(used_pct, 1)},
            )
        except Exception:
            return ComponentHealth(name="storage", status="healthy", details={})

    @staticmethod
    async def _check_npu(npu: Any = None) -> ComponentHealth:
        """Check NPU health."""
        if npu is None:
            return ComponentHealth(name="npu", status="healthy", details={})
        try:
            status_obj = await npu.get_status()
            details = {
                "temp_c": status_obj.temperature_c,
                "memory_used_mb": status_obj.memory_used_mb,
                "memory_total_mb": status_obj.memory_total_mb,
            }
            status = "healthy"
            if status_obj.temperature_c > 85:
                status = "unhealthy"
            elif status_obj.temperature_c > 75:
                status = "degraded"
            return ComponentHealth(name="npu", status=status, details=details)
        except Exception:
            return ComponentHealth(name="npu", status="unhealthy", details={"error": "unreachable"})
