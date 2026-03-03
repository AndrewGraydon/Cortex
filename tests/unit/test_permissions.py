"""Tests for permission engine — tier-based access control."""

from __future__ import annotations

from cortex.security.approval import ApprovalManager
from cortex.security.permissions import PermissionEngine
from cortex.security.types import ApprovalStatus, PermissionTier


class TestTier0Safe:
    async def test_safe_always_allowed(self) -> None:
        engine = PermissionEngine()
        check = await engine.check("clock", PermissionTier.SAFE)
        assert check.allowed
        assert check.status == ApprovalStatus.AUTO_APPROVED

    async def test_safe_no_approval_manager_needed(self) -> None:
        engine = PermissionEngine(approval_manager=None)
        check = await engine.check("system_info", PermissionTier.SAFE)
        assert check.allowed


class TestTier1Normal:
    async def test_normal_auto_approved(self) -> None:
        engine = PermissionEngine()
        check = await engine.check("timer_set", PermissionTier.NORMAL)
        assert check.allowed
        assert check.status == ApprovalStatus.AUTO_APPROVED


class TestTier2Risky:
    async def test_risky_denied_without_approval_manager(self) -> None:
        engine = PermissionEngine(approval_manager=None)
        check = await engine.check("timer_cancel", PermissionTier.RISKY)
        assert not check.allowed
        assert check.status == ApprovalStatus.TIMEOUT

    async def test_risky_approved_with_button(self) -> None:
        from cortex.hal.display.button import ButtonStateMachine
        from cortex.hal.display.mock import MockDisplayService

        display = MockDisplayService()
        button = ButtonStateMachine()

        manager = ApprovalManager(
            display=display,
            button=button,
            timeout_seconds=2.0,
        )
        engine = PermissionEngine(approval_manager=manager)

        # Simulate button approval in background
        import asyncio

        async def approve_after_delay():
            await asyncio.sleep(0.1)
            button.on_press()
            await asyncio.sleep(0.05)
            button.on_release()  # Short press → single_click

        task = asyncio.create_task(approve_after_delay())
        check = await engine.check("timer_cancel", PermissionTier.RISKY)
        await task
        assert check.allowed
        assert check.status == ApprovalStatus.USER_APPROVED

    async def test_risky_denied_with_long_press(self) -> None:
        from cortex.hal.display.button import ButtonStateMachine
        from cortex.hal.display.mock import MockDisplayService

        display = MockDisplayService()
        button = ButtonStateMachine()

        manager = ApprovalManager(
            display=display,
            button=button,
            timeout_seconds=5.0,
        )
        engine = PermissionEngine(approval_manager=manager)

        import asyncio

        async def deny_after_delay():
            await asyncio.sleep(0.1)
            button.on_press()
            await asyncio.sleep(2.1)  # >2s = long press
            button.on_release()

        task = asyncio.create_task(deny_after_delay())
        check = await engine.check("timer_cancel", PermissionTier.RISKY)
        await task
        assert not check.allowed
        assert check.status == ApprovalStatus.USER_DENIED


class TestTier3Danger:
    async def test_danger_denied_without_approval_manager(self) -> None:
        engine = PermissionEngine(approval_manager=None)
        check = await engine.check("system_reboot", PermissionTier.DANGER)
        assert not check.allowed

    async def test_danger_requires_approval(self) -> None:
        from cortex.hal.display.button import ButtonStateMachine
        from cortex.hal.display.mock import MockDisplayService

        display = MockDisplayService()
        button = ButtonStateMachine()

        manager = ApprovalManager(
            display=display,
            button=button,
            timeout_seconds=1.0,
        )
        engine = PermissionEngine(approval_manager=manager)

        # Let it timeout
        check = await engine.check("system_reboot", PermissionTier.DANGER)
        assert not check.allowed
        assert check.status == ApprovalStatus.TIMEOUT


class TestMakeAuditEntry:
    async def test_creates_audit_entry(self) -> None:
        engine = PermissionEngine()
        check = await engine.check("clock", PermissionTier.SAFE)
        entry = engine.make_audit_entry(
            action_type="tool_call",
            action_id="clock",
            check=check,
            tier=PermissionTier.SAFE,
        )
        assert entry.action_type == "tool_call"
        assert entry.action_id == "clock"
        assert entry.approval_status == "auto"
        assert entry.result == "success"
        assert len(entry.id) == 16

    async def test_denied_entry(self) -> None:
        engine = PermissionEngine()
        check = await engine.check("system_reboot", PermissionTier.RISKY)
        entry = engine.make_audit_entry(
            action_type="tool_call",
            action_id="system_reboot",
            check=check,
            tier=PermissionTier.RISKY,
            parameters={"reason": "update"},
        )
        assert entry.result == "denied"
        assert entry.parameters == {"reason": "update"}
