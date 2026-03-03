"""Tests for tool registry and action engine."""

from __future__ import annotations

import pytest

from cortex.agent.action_engine import ActionEngine
from cortex.agent.tools.builtin.calculator import CalculatorTool
from cortex.agent.tools.builtin.clock import ClockTool
from cortex.agent.tools.builtin.timer import TimerSetTool, TimerStore, set_timer_store
from cortex.agent.tools.registry import ToolRegistry
from cortex.agent.types import ToolCall
from cortex.security.audit import SqliteAuditLog
from cortex.security.permissions import PermissionEngine
from cortex.security.types import PermissionTier


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(ClockTool())
    reg.register(CalculatorTool())
    return reg


class TestToolRegistry:
    def test_register_and_get(self, registry: ToolRegistry) -> None:
        assert registry.get("clock") is not None
        assert registry.get("calculator") is not None
        assert registry.get("nonexistent") is None

    def test_tool_names(self, registry: ToolRegistry) -> None:
        names = registry.tool_names
        assert "clock" in names
        assert "calculator" in names

    def test_len(self, registry: ToolRegistry) -> None:
        assert len(registry) == 2

    def test_get_schemas(self, registry: ToolRegistry) -> None:
        schemas = registry.get_schemas()
        assert len(schemas) == 2
        names = {s.name for s in schemas}
        assert "clock" in names
        assert "calculator" in names

    def test_get_schemas_filtered(self, registry: ToolRegistry) -> None:
        schemas = registry.get_schemas(["clock"])
        assert len(schemas) == 1
        assert schemas[0].name == "clock"

    def test_get_tier(self, registry: ToolRegistry) -> None:
        assert registry.get_tier("clock") == PermissionTier.SAFE
        assert registry.get_tier("calculator") == PermissionTier.SAFE

    def test_unknown_tool_tier_danger(self, registry: ToolRegistry) -> None:
        assert registry.get_tier("unknown") == PermissionTier.DANGER

    async def test_execute_tool(self, registry: ToolRegistry) -> None:
        call = ToolCall(name="calculator", arguments={"expression": "2+2"})
        result = await registry.execute(call)
        assert result.success
        assert result.data == 4

    async def test_execute_unknown_tool(self, registry: ToolRegistry) -> None:
        call = ToolCall(name="nonexistent", arguments={})
        result = await registry.execute(call)
        assert not result.success
        assert "Unknown tool" in result.error


class TestActionEngine:
    @pytest.fixture(autouse=True)
    def fresh_timer_store(self) -> None:
        set_timer_store(TimerStore())

    async def test_execute_safe_tool(self, registry: ToolRegistry) -> None:
        engine = ActionEngine(registry=registry)
        call = ToolCall(name="clock", arguments={})
        result = await engine.execute(call)
        assert result.success

    async def test_execute_with_permissions(self, registry: ToolRegistry) -> None:
        perms = PermissionEngine()
        engine = ActionEngine(registry=registry, permissions=perms)
        call = ToolCall(name="clock", arguments={})
        result = await engine.execute(call)
        assert result.success

    async def test_execute_with_audit(self, registry: ToolRegistry, tmp_path) -> None:
        audit = SqliteAuditLog(db_path=str(tmp_path / "audit.db"))
        await audit.start()
        try:
            engine = ActionEngine(
                registry=registry,
                permissions=PermissionEngine(),
                audit_log=audit,
            )
            call = ToolCall(
                name="calculator",
                arguments={"expression": "6 * 7"},
            )
            result = await engine.execute(call)
            assert result.success

            entries = await audit.query()
            assert len(entries) == 1
            assert entries[0].action_id == "calculator"
            assert entries[0].result == "success"
        finally:
            await audit.stop()

    async def test_permission_denied_logged(self, registry: ToolRegistry, tmp_path) -> None:
        # Register a tier-2 tool
        registry.register(TimerSetTool())
        audit = SqliteAuditLog(db_path=str(tmp_path / "audit.db"))
        await audit.start()
        try:
            # No approval manager → tier 2 denied
            perms = PermissionEngine(approval_manager=None)
            # Override tier to RISKY for this test
            original_tier = registry.get_tier
            registry.get_tier = lambda name: (
                PermissionTier.RISKY if name == "timer_set" else original_tier(name)
            )
            engine = ActionEngine(registry=registry, permissions=perms, audit_log=audit)
            call = ToolCall(name="timer_set", arguments={"duration": 60})
            result = await engine.execute(call)
            assert not result.success
            assert "Permission denied" in result.error

            entries = await audit.query()
            assert len(entries) == 1
            assert entries[0].result == "denied"
        finally:
            await audit.stop()
