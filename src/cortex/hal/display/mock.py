"""Mock display service for off-Pi development and testing.

Records all state transitions and LED changes for verification.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from cortex.hal.types import ButtonEvent, ButtonGesture, DisplayState, LedColor


@dataclass
class MockDisplayService:
    """Mock display — records operations for testing.

    Implements the DisplayService Protocol.
    """

    _state: DisplayState = DisplayState.IDLE
    _current_text: str = ""
    _led_color: LedColor = field(default_factory=LedColor.off)
    _state_history: list[tuple[DisplayState, str]] = field(default_factory=list)
    _led_history: list[LedColor] = field(default_factory=list)

    async def set_state(self, state: DisplayState, text: str = "") -> None:
        self._state = state
        self._current_text = text
        self._state_history.append((state, text))

    async def set_led(self, color: LedColor) -> None:
        self._led_color = color
        self._led_history.append(color)

    async def show_text(self, text: str, scroll: bool = False) -> None:
        self._current_text = text

    async def get_state(self) -> DisplayState:
        return self._state


@dataclass
class MockButtonService:
    """Mock button service — allows injecting gestures for testing.

    Implements the ButtonService Protocol.
    """

    _events: list[ButtonEvent] = field(default_factory=list)
    _event_index: int = 0

    def inject_gesture(self, gesture: ButtonGesture, duration_ms: float = 0.0) -> None:
        """Add a gesture event to the queue."""
        import time

        self._events.append(
            ButtonEvent(gesture=gesture, timestamp=time.monotonic(), duration_ms=duration_ms)
        )

    async def wait_gesture(self) -> ButtonEvent:
        """Return next injected gesture (blocks if none available)."""
        while self._event_index >= len(self._events):
            import asyncio

            await asyncio.sleep(0.01)
        event = self._events[self._event_index]
        self._event_index += 1
        return event

    def subscribe(self) -> AsyncIterator[ButtonEvent]:
        return self._subscribe_impl()

    async def _subscribe_impl(self) -> AsyncIterator[ButtonEvent]:
        while True:
            event = await self.wait_gesture()
            yield event
