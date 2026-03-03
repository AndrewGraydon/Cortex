"""Tests for button-driven approval flow."""

from __future__ import annotations

import asyncio

import pytest

from cortex.hal.display.button import ButtonStateMachine
from cortex.hal.types import DisplayState
from cortex.security.approval import ApprovalManager
from cortex.security.types import ApprovalRequest, ApprovalStatus, PermissionTier


class MockDisplayForApproval:
    """Minimal mock display for approval tests."""

    def __init__(self) -> None:
        self.states: list[tuple[DisplayState, str]] = []

    async def set_state(self, state: DisplayState, text: str = "") -> None:
        self.states.append((state, text))


@pytest.fixture
def display() -> MockDisplayForApproval:
    return MockDisplayForApproval()


@pytest.fixture
def button() -> ButtonStateMachine:
    return ButtonStateMachine()


@pytest.fixture
def manager(display, button) -> ApprovalManager:
    return ApprovalManager(
        display=display,
        button=button,
        timeout_seconds=2.0,
    )


def make_request(
    action_id: str = "test_action",
    tier: PermissionTier = PermissionTier.RISKY,
) -> ApprovalRequest:
    return ApprovalRequest(
        request_id="req-001",
        action_id=action_id,
        action_description=f"Execute {action_id}",
        permission_tier=tier,
    )


class TestApprovalWithSingleClick:
    async def test_single_click_approves(self, manager, button) -> None:
        async def click():
            await asyncio.sleep(0.1)
            button.on_press()
            await asyncio.sleep(0.05)
            button.on_release()

        task = asyncio.create_task(click())
        result = await manager.request_approval(make_request())
        await task
        assert result == ApprovalStatus.USER_APPROVED

    async def test_approval_clears_pending(self, manager, button) -> None:
        async def click():
            await asyncio.sleep(0.1)
            button.on_press()
            await asyncio.sleep(0.05)
            button.on_release()

        task = asyncio.create_task(click())
        await manager.request_approval(make_request())
        await task
        assert manager.pending is None


class TestApprovalWithLongPress:
    async def test_long_press_denies(self, manager, button) -> None:
        async def long_press():
            await asyncio.sleep(0.1)
            button.on_press()
            await asyncio.sleep(2.1)
            button.on_release()

        task = asyncio.create_task(long_press())
        result = await manager.request_approval(make_request())
        await task
        assert result == ApprovalStatus.USER_DENIED


class TestApprovalTimeout:
    async def test_timeout_denies(self) -> None:
        button = ButtonStateMachine()
        manager = ApprovalManager(
            display=MockDisplayForApproval(),
            button=button,
            timeout_seconds=0.3,
        )
        result = await manager.request_approval(make_request())
        assert result == ApprovalStatus.TIMEOUT

    async def test_timeout_recorded_in_history(self) -> None:
        button = ButtonStateMachine()
        manager = ApprovalManager(
            display=MockDisplayForApproval(),
            button=button,
            timeout_seconds=0.3,
        )
        await manager.request_approval(make_request())
        assert len(manager.history) == 1
        assert manager.history[0][1] == ApprovalStatus.TIMEOUT


class TestApprovalDisplay:
    async def test_shows_alert_state(self, manager, display, button) -> None:
        async def click():
            await asyncio.sleep(0.1)
            button.on_press()
            await asyncio.sleep(0.05)
            button.on_release()

        task = asyncio.create_task(click())
        await manager.request_approval(make_request())
        await task

        # Should have shown ALERT and then restored to IDLE
        alert_states = [s for s in display.states if s[0] == DisplayState.ALERT]
        assert len(alert_states) == 1
        assert "Approve" in alert_states[0][1]

        idle_states = [s for s in display.states if s[0] == DisplayState.IDLE]
        assert len(idle_states) >= 1

    async def test_prompt_contains_action_description(self, manager, display, button) -> None:
        async def click():
            await asyncio.sleep(0.1)
            button.on_press()
            await asyncio.sleep(0.05)
            button.on_release()

        task = asyncio.create_task(click())
        req = make_request(action_id="timer_cancel")
        await manager.request_approval(req)
        await task

        alert_text = [s[1] for s in display.states if s[0] == DisplayState.ALERT][0]
        assert "timer_cancel" in alert_text


class TestApprovalNoServices:
    async def test_no_button_denies(self) -> None:
        manager = ApprovalManager(
            display=MockDisplayForApproval(),
            button=None,
            timeout_seconds=1.0,
        )
        result = await manager.request_approval(make_request())
        assert result == ApprovalStatus.TIMEOUT

    async def test_no_display_still_works(self, button) -> None:
        manager = ApprovalManager(
            display=None,
            button=button,
            timeout_seconds=0.3,
        )
        result = await manager.request_approval(make_request())
        # Times out because no one clicks
        assert result == ApprovalStatus.TIMEOUT


class TestApprovalHistory:
    async def test_history_accumulates(self, manager, button) -> None:
        # First: timeout
        manager_short = ApprovalManager(
            display=MockDisplayForApproval(),
            button=button,
            timeout_seconds=0.2,
        )
        await manager_short.request_approval(make_request(action_id="action_1"))

        # Second: approve
        async def click():
            await asyncio.sleep(0.1)
            button.on_press()
            await asyncio.sleep(0.05)
            button.on_release()

        task = asyncio.create_task(click())
        await manager_short.request_approval(make_request(action_id="action_2"))
        await task

        assert len(manager_short.history) == 2
        assert manager_short.history[0][1] == ApprovalStatus.TIMEOUT
        assert manager_short.history[1][1] == ApprovalStatus.USER_APPROVED


class TestPendingState:
    async def test_pending_set_during_approval(self, manager, button) -> None:
        pending_during = None

        async def check_pending():
            await asyncio.sleep(0.05)
            nonlocal pending_during
            pending_during = manager.pending
            # Now click to resolve
            button.on_press()
            await asyncio.sleep(0.05)
            button.on_release()

        task = asyncio.create_task(check_pending())
        await manager.request_approval(make_request())
        await task
        assert pending_during is not None
        assert pending_during.action_id == "test_action"
        assert manager.pending is None
