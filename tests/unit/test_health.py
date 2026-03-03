"""Tests for health monitoring."""

from __future__ import annotations

from pathlib import Path

from cortex.agent.health import ComponentHealth, HealthMonitor, SystemHealth
from cortex.hal.npu.mock import MockNpuService


class TestComponentHealth:
    def test_default_healthy(self) -> None:
        c = ComponentHealth(name="test")
        assert c.status == "healthy"
        assert c.details == {}


class TestSystemHealth:
    def test_to_dict(self) -> None:
        health = SystemHealth(
            status="healthy",
            uptime_seconds=123.4,
            components=[
                ComponentHealth(name="cpu", status="healthy", details={"load_1m": 0.5}),
                ComponentHealth(name="memory", status="healthy", details={"used_pct": 45.0}),
            ],
            models_loaded=["sensevoice", "qwen3-1.7b"],
            timestamp=1000.0,
        )
        d = health.to_dict()
        assert d["status"] == "healthy"
        assert d["uptime_seconds"] == 123.4
        assert "cpu" in d["components"]
        assert d["components"]["cpu"]["load_1m"] == 0.5
        assert "sensevoice" in d["models_loaded"]

    def test_to_dict_structure(self) -> None:
        health = SystemHealth(
            status="degraded",
            uptime_seconds=0.0,
            components=[],
            models_loaded=[],
        )
        d = health.to_dict()
        assert "status" in d
        assert "uptime_seconds" in d
        assert "components" in d
        assert "models_loaded" in d
        assert "timestamp" in d


class TestHealthMonitorBasic:
    async def test_check_without_npu(self) -> None:
        monitor = HealthMonitor()
        health = await monitor.check()
        assert health.status in ("healthy", "degraded", "unhealthy")
        assert health.uptime_seconds >= 0
        # Should have CPU, memory, storage
        names = [c.name for c in health.components]
        assert "cpu" in names
        assert "memory" in names
        assert "storage" in names

    async def test_uptime_increases(self) -> None:
        monitor = HealthMonitor()
        u1 = monitor.uptime_seconds
        import asyncio

        await asyncio.sleep(0.05)
        u2 = monitor.uptime_seconds
        assert u2 > u1


class TestHealthMonitorWithNpu:
    async def test_check_with_mock_npu(self) -> None:
        npu = MockNpuService()
        await npu.load_model("sensevoice", Path("/mock/sv"))
        await npu.load_model("qwen3-1.7b", Path("/mock/qwen"))

        monitor = HealthMonitor(npu=npu)
        health = await monitor.check()
        assert "sensevoice" in health.models_loaded
        assert "qwen3-1.7b" in health.models_loaded
        # NPU component should be present
        npu_comp = [c for c in health.components if c.name == "npu"]
        assert len(npu_comp) == 1
        assert npu_comp[0].status == "healthy"

    async def test_health_json_valid(self) -> None:
        import json

        npu = MockNpuService()
        await npu.load_model("sensevoice", Path("/mock/sv"))
        monitor = HealthMonitor(npu=npu)
        health = await monitor.check()
        d = health.to_dict()
        # Should be JSON-serializable
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["status"] == health.status


class TestCpuCheck:
    def test_cpu_returns_component(self) -> None:
        comp = HealthMonitor._check_cpu()
        assert comp.name == "cpu"
        assert "load_1m" in comp.details


class TestStorageCheck:
    def test_storage_returns_component(self) -> None:
        comp = HealthMonitor._check_storage()
        assert comp.name == "storage"
        assert "used_pct" in comp.details
