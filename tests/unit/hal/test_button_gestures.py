"""Tests for button gesture state machine.

Tests the pure logic of ButtonStateMachine without GPIO hardware.
"""

from __future__ import annotations

import asyncio

import pytest

from cortex.hal.display.button import (
    HOLD_THRESHOLD,
    ButtonStateMachine,
)
from cortex.hal.types import ButtonGesture


@pytest.fixture
def button() -> ButtonStateMachine:
    return ButtonStateMachine()


class TestHoldGesture:
    async def test_hold_start_fires_after_threshold(self, button: ButtonStateMachine) -> None:
        """Press held > 300ms fires hold_start."""
        button.on_press()
        await asyncio.sleep(HOLD_THRESHOLD + 0.05)
        event = button._event_queue.get_nowait()
        assert event.gesture == ButtonGesture.HOLD_START

    async def test_hold_end_on_release(self, button: ButtonStateMachine) -> None:
        """Release after hold fires hold_end."""
        button.on_press()
        await asyncio.sleep(HOLD_THRESHOLD + 0.05)
        # Consume hold_start
        await asyncio.wait_for(button.wait_gesture(), timeout=0.1)

        button.on_release()
        event = await asyncio.wait_for(button.wait_gesture(), timeout=0.1)
        assert event.gesture == ButtonGesture.HOLD_END
        assert event.duration_ms > HOLD_THRESHOLD * 1000

    async def test_long_press(self, button: ButtonStateMachine) -> None:
        """Press held > 2s fires long_press instead of hold_end."""
        button.on_press()
        await asyncio.sleep(HOLD_THRESHOLD + 0.05)
        # Consume hold_start
        await asyncio.wait_for(button.wait_gesture(), timeout=0.1)

        await asyncio.sleep(2.0 - HOLD_THRESHOLD)
        button.on_release()
        event = await asyncio.wait_for(button.wait_gesture(), timeout=0.1)
        assert event.gesture == ButtonGesture.LONG_PRESS
        assert event.duration_ms >= 2000


class TestClickGestures:
    async def test_single_click(self, button: ButtonStateMachine) -> None:
        """Quick press+release = single click (after multi-click window)."""
        button.on_press()
        await asyncio.sleep(0.05)
        button.on_release()

        event = await asyncio.wait_for(button.wait_gesture(), timeout=1.0)
        assert event.gesture == ButtonGesture.SINGLE_CLICK

    async def test_double_click(self, button: ButtonStateMachine) -> None:
        """Two quick presses within 400ms = double click."""
        # First click
        button.on_press()
        await asyncio.sleep(0.05)
        button.on_release()

        # Second click (within window)
        await asyncio.sleep(0.1)
        button.on_press()
        await asyncio.sleep(0.05)
        button.on_release()

        event = await asyncio.wait_for(button.wait_gesture(), timeout=1.0)
        assert event.gesture == ButtonGesture.DOUBLE_CLICK

    async def test_triple_click(self, button: ButtonStateMachine) -> None:
        """Three quick presses = triple click."""
        for _ in range(3):
            button.on_press()
            await asyncio.sleep(0.05)
            button.on_release()
            await asyncio.sleep(0.1)

        event = await asyncio.wait_for(button.wait_gesture(), timeout=1.0)
        assert event.gesture == ButtonGesture.TRIPLE_CLICK

    async def test_single_click_not_premature(self, button: ButtonStateMachine) -> None:
        """Single click waits for multi-click window before emitting."""
        button.on_press()
        await asyncio.sleep(0.05)
        button.on_release()

        # Should NOT have event immediately
        assert button._event_queue.empty()

        # Wait for resolution
        event = await asyncio.wait_for(button.wait_gesture(), timeout=1.0)
        assert event.gesture == ButtonGesture.SINGLE_CLICK


class TestMockDisplay:
    async def test_state_transitions(self) -> None:
        from cortex.hal.display.mock import MockDisplayService
        from cortex.hal.types import DisplayState

        display = MockDisplayService()
        await display.set_state(DisplayState.LISTENING, "Listening...")
        await display.set_state(DisplayState.THINKING, "Thinking...")
        await display.set_state(DisplayState.SPEAKING, "Hello world")

        assert len(display._state_history) == 3
        assert display._state_history[0] == (DisplayState.LISTENING, "Listening...")
        assert display._state_history[2] == (DisplayState.SPEAKING, "Hello world")
        assert await display.get_state() == DisplayState.SPEAKING

    async def test_mock_button_inject(self) -> None:
        from cortex.hal.display.mock import MockButtonService

        btn = MockButtonService()
        btn.inject_gesture(ButtonGesture.HOLD_START)
        btn.inject_gesture(ButtonGesture.HOLD_END, duration_ms=500.0)

        e1 = await asyncio.wait_for(btn.wait_gesture(), timeout=0.5)
        e2 = await asyncio.wait_for(btn.wait_gesture(), timeout=0.5)
        assert e1.gesture == ButtonGesture.HOLD_START
        assert e2.gesture == ButtonGesture.HOLD_END
        assert e2.duration_ms == 500.0
