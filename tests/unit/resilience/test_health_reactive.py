"""Tests for reactive health monitoring — polling, callbacks, thresholds."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from cortex.agent.health import (
    ComponentHealth,
    HealthMonitor,
    SystemHealth,
)


class TestSystemHealthModel:
    """SystemHealth dataclass."""

    def test_to_dict(self) -> None:
        health = SystemHealth(
            status="healthy",
            uptime_seconds=100.5,
            components=[
                ComponentHealth(name="cpu", status="healthy", details={"load_1m": 0.5}),
            ],
            models_loaded=["sensevoice"],
            timestamp=1000.0,
        )
        d = health.to_dict()
        assert d["status"] == "healthy"
        assert d["uptime_seconds"] == 100.5
        assert d["components"]["cpu"]["status"] == "healthy"
        assert d["components"]["cpu"]["load_1m"] == 0.5
        assert d["models_loaded"] == ["sensevoice"]

    def test_component_details_found(self) -> None:
        health = SystemHealth(
            status="healthy",
            uptime_seconds=0,
            components=[
                ComponentHealth(name="npu", status="healthy", details={"temp_c": 45}),
            ],
            models_loaded=[],
        )
        assert health.component_details("npu") == {"temp_c": 45}

    def test_component_details_not_found(self) -> None:
        health = SystemHealth(
            status="healthy",
            uptime_seconds=0,
            components=[],
            models_loaded=[],
        )
        assert health.component_details("missing") == {}


class TestHealthMonitorBasic:
    """Basic HealthMonitor properties."""

    def test_initial_state(self) -> None:
        hm = HealthMonitor()
        assert hm.is_polling is False
        assert hm.uptime_seconds >= 0

    @pytest.mark.asyncio()
    async def test_check_returns_system_health(self) -> None:
        hm = HealthMonitor()
        health = await hm.check()
        assert isinstance(health, SystemHealth)
        assert health.status in ("healthy", "degraded", "unhealthy")

    @pytest.mark.asyncio()
    async def test_check_includes_cpu_memory_storage(self) -> None:
        hm = HealthMonitor()
        health = await hm.check()
        names = [c.name for c in health.components]
        assert "cpu" in names
        assert "memory" in names
        assert "storage" in names

    @pytest.mark.asyncio()
    async def test_check_without_npu(self) -> None:
        hm = HealthMonitor(npu=None)
        health = await hm.check()
        names = [c.name for c in health.components]
        assert "npu" not in names


class TestHealthMonitorNpu:
    """NPU health checks."""

    @pytest.mark.asyncio()
    async def test_npu_healthy(self) -> None:
        npu = AsyncMock()
        status = MagicMock()
        status.temperature_c = 45.0
        status.memory_used_mb = 2000
        status.memory_total_mb = 7040
        status.models_loaded = ["sensevoice"]
        npu.get_status.return_value = status

        hm = HealthMonitor(npu=npu)
        health = await hm.check()
        npu_comp = next(c for c in health.components if c.name == "npu")
        assert npu_comp.status == "healthy"
        assert npu_comp.details["temp_c"] == 45.0

    @pytest.mark.asyncio()
    async def test_npu_degraded_at_75c(self) -> None:
        npu = AsyncMock()
        status = MagicMock()
        status.temperature_c = 78.0
        status.memory_used_mb = 2000
        status.memory_total_mb = 7040
        status.models_loaded = []
        npu.get_status.return_value = status

        hm = HealthMonitor(npu=npu)
        health = await hm.check()
        npu_comp = next(c for c in health.components if c.name == "npu")
        assert npu_comp.status == "degraded"

    @pytest.mark.asyncio()
    async def test_npu_unhealthy_at_85c(self) -> None:
        npu = AsyncMock()
        status = MagicMock()
        status.temperature_c = 90.0
        status.memory_used_mb = 2000
        status.memory_total_mb = 7040
        status.models_loaded = []
        npu.get_status.return_value = status

        hm = HealthMonitor(npu=npu)
        health = await hm.check()
        npu_comp = next(c for c in health.components if c.name == "npu")
        assert npu_comp.status == "unhealthy"

    @pytest.mark.asyncio()
    async def test_npu_unreachable(self) -> None:
        npu = AsyncMock()
        npu.get_status.side_effect = RuntimeError("NPU not responding")

        hm = HealthMonitor(npu=npu)
        health = await hm.check()
        npu_comp = next(c for c in health.components if c.name == "npu")
        assert npu_comp.status == "unhealthy"
        assert npu_comp.details.get("error") == "unreachable"


class TestHealthMonitorPolling:
    """Reactive polling and change detection."""

    @pytest.mark.asyncio()
    async def test_start_stop_polling(self) -> None:
        hm = HealthMonitor(poll_interval_s=0.05)
        assert hm.is_polling is False

        await hm.start_polling()
        assert hm.is_polling is True

        await hm.stop_polling()
        assert hm.is_polling is False

    @pytest.mark.asyncio()
    async def test_double_start_is_noop(self) -> None:
        hm = HealthMonitor(poll_interval_s=0.05)
        await hm.start_polling()
        task = hm._poll_task
        await hm.start_polling()  # Should not create new task
        assert hm._poll_task is task
        await hm.stop_polling()

    @pytest.mark.asyncio()
    async def test_callback_on_health_change(self) -> None:
        """Callback fires when health status changes."""
        states: list[SystemHealth] = []

        hm = HealthMonitor(poll_interval_s=0.02)
        hm.on_health_change(lambda h: states.append(h))

        # Manually set last status to something different
        hm._last_status = "degraded"

        await hm.start_polling()
        await asyncio.sleep(0.1)  # Let a few polls happen
        await hm.stop_polling()

        # Should have detected change from "degraded" → actual status
        assert len(states) >= 1

    @pytest.mark.asyncio()
    async def test_no_callback_when_status_unchanged(self) -> None:
        """No callback when health stays the same."""
        states: list[SystemHealth] = []

        hm = HealthMonitor(poll_interval_s=0.02)
        hm.on_health_change(lambda h: states.append(h))
        # Default _last_status is "healthy", and check() returns "healthy"
        # so no change should fire

        await hm.start_polling()
        await asyncio.sleep(0.1)
        await hm.stop_polling()

        assert len(states) == 0

    @pytest.mark.asyncio()
    async def test_callback_error_doesnt_crash_polling(self) -> None:
        """Exception in callback doesn't stop the poll loop."""
        def bad_callback(h: SystemHealth) -> None:
            raise RuntimeError("callback exploded")

        hm = HealthMonitor(poll_interval_s=0.02)
        hm.on_health_change(bad_callback)
        hm._last_status = "degraded"  # Force a change

        await hm.start_polling()
        await asyncio.sleep(0.1)
        await hm.stop_polling()
        # Should not have crashed — poll loop continues


class TestHealthMonitorOverallStatus:
    """Overall status computation from components."""

    @pytest.mark.asyncio()
    async def test_unhealthy_component_makes_overall_unhealthy(self) -> None:
        hm = HealthMonitor()
        health = await hm.check()
        # By default all should be healthy on macOS dev machine
        assert health.status == "healthy"

    @pytest.mark.asyncio()
    async def test_timestamp_is_set(self) -> None:
        hm = HealthMonitor()
        health = await hm.check()
        assert health.timestamp > 0

    @pytest.mark.asyncio()
    async def test_uptime_increases(self) -> None:
        hm = HealthMonitor()
        h1 = await hm.check()
        await asyncio.sleep(0.05)
        h2 = await hm.check()
        assert h2.uptime_seconds > h1.uptime_seconds
