"""Button gesture state machine.

Hardware: GPIO 11 (BOARD numbering), active-HIGH (pressed=1).
Gestures detected (DD-021):
  - hold_start: Press held >300ms (fires immediately at threshold)
  - hold_end: Release after hold
  - single_click: Press <300ms, no second press within 400ms
  - double_click: Two presses <400ms apart
  - triple_click: Three presses <600ms apart
  - long_press: Hold >2s

The state machine is pure logic — GPIO polling is handled by the
service layer (or injected for testing).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from cortex.hal.types import ButtonEvent, ButtonGesture

logger = logging.getLogger(__name__)

# Gesture timing thresholds (seconds)
HOLD_THRESHOLD = 0.300  # Press > 300ms = hold
LONG_PRESS_THRESHOLD = 2.0  # Hold > 2s = long press
MULTI_CLICK_WINDOW = 0.400  # Max gap between clicks for double/triple
TRIPLE_CLICK_WINDOW = 0.600  # Total window for triple click


class ButtonStateMachine:
    """Pure gesture detection logic.

    Feed button state changes via on_press() and on_release().
    Retrieve events via get_event() or subscribe().

    Thread-safety: on_press()/on_release() may be called from any thread
    (e.g. RPi.GPIO callback thread). The event loop reference is captured
    at construction time and coroutines are scheduled thread-safely.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        self._loop = loop
        self._press_time: float = 0.0
        self._release_times: list[float] = []
        self._is_pressed = False
        self._is_holding = False
        self._hold_fired = False
        self._event_queue: asyncio.Queue[ButtonEvent] = asyncio.Queue()
        self._hold_handle: Any = None  # Task or concurrent.futures.Future
        self._click_handle: Any = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the event loop for thread-safe scheduling."""
        self._loop = loop

    def _schedule(self, coro: Any) -> Any:
        """Schedule a coroutine, detecting whether we're in the loop thread.

        From the event loop thread: uses ensure_future (immediate scheduling).
        From other threads (GPIO callback): uses run_coroutine_threadsafe.
        Both return objects supporting .cancel() and .done().
        """
        try:
            asyncio.get_running_loop()
            # We're in an async context — ensure_future works
            return asyncio.ensure_future(coro)
        except RuntimeError:
            # No running loop in this thread (e.g. GPIO callback)
            if self._loop is None:
                logger.error("No event loop for button state machine")
                return None
            return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def on_press(self) -> None:
        """Called when button is pressed (goes HIGH). Thread-safe."""
        now = time.monotonic()
        self._is_pressed = True
        self._press_time = now
        self._hold_fired = False

        # Cancel any pending click resolution
        if self._click_handle and not self._click_handle.done():
            self._click_handle.cancel()

        # Start hold detection timer
        self._hold_handle = self._schedule(self._detect_hold(now))

    def on_release(self) -> None:
        """Called when button is released (goes LOW). Thread-safe."""
        now = time.monotonic()
        self._is_pressed = False
        press_duration = now - self._press_time

        # Cancel hold detection
        if self._hold_handle and not self._hold_handle.done():
            self._hold_handle.cancel()
            self._hold_handle = None

        if self._is_holding:
            # End of hold
            self._is_holding = False
            if press_duration >= LONG_PRESS_THRESHOLD:
                self._emit(ButtonGesture.LONG_PRESS, duration_ms=press_duration * 1000)
            else:
                self._emit(ButtonGesture.HOLD_END, duration_ms=press_duration * 1000)
            self._release_times.clear()
            return

        if self._hold_fired:
            # Hold was detected but we're handling the release
            self._release_times.clear()
            return

        # Short press — accumulate for click counting
        self._release_times.append(now)

        # Start/restart click resolution timer
        self._click_handle = self._schedule(self._resolve_clicks())

    async def wait_gesture(self) -> ButtonEvent:
        """Wait for the next gesture event."""
        return await self._event_queue.get()

    async def subscribe(self) -> AsyncIterator[ButtonEvent]:
        """Async iterator of gesture events."""
        while True:
            event = await self._event_queue.get()
            yield event

    async def _detect_hold(self, press_start: float) -> None:
        """Wait for hold threshold, then emit hold_start."""
        try:
            await asyncio.sleep(HOLD_THRESHOLD)
            if self._is_pressed and self._press_time == press_start:
                self._is_holding = True
                self._hold_fired = True
                self._emit(ButtonGesture.HOLD_START)
                self._release_times.clear()
        except asyncio.CancelledError:
            pass

    async def _resolve_clicks(self) -> None:
        """Wait for multi-click window, then emit click gesture."""
        try:
            await asyncio.sleep(MULTI_CLICK_WINDOW)

            count = len(self._release_times)
            self._release_times.clear()

            if count >= 3:
                self._emit(ButtonGesture.TRIPLE_CLICK)
            elif count == 2:
                self._emit(ButtonGesture.DOUBLE_CLICK)
            elif count == 1:
                self._emit(ButtonGesture.SINGLE_CLICK)
        except asyncio.CancelledError:
            pass

    def _emit(self, gesture: ButtonGesture, duration_ms: float = 0.0) -> None:
        """Emit a gesture event."""
        event = ButtonEvent(
            gesture=gesture,
            timestamp=time.monotonic(),
            duration_ms=duration_ms,
        )
        self._event_queue.put_nowait(event)
        logger.debug("Button gesture: %s (%.0fms)", gesture.value, duration_ms)


class GpioButtonService:
    """Button service using RPi.GPIO for real hardware.

    Wraps ButtonStateMachine with GPIO edge detection.
    Pi-only — requires RPi.GPIO package.
    """

    def __init__(self, pin: int = 11, bounce_ms: int = 20) -> None:
        self._pin = pin
        self._bounce_ms = bounce_ms
        self._state_machine: ButtonStateMachine | None = None
        self._gpio: Any = None

    async def start(self) -> None:
        """Initialize GPIO and start edge detection."""
        # Create state machine with current event loop for thread-safe GPIO callbacks
        self._state_machine = ButtonStateMachine(loop=asyncio.get_running_loop())
        try:
            import RPi.GPIO as GPIO  # type: ignore[import-untyped]
        except ImportError as e:
            msg = "RPi.GPIO not available — not running on Pi?"
            raise RuntimeError(msg) from e

        self._gpio = GPIO
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(self._pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.add_event_detect(
            self._pin,
            GPIO.BOTH,
            callback=self._gpio_callback,
            bouncetime=self._bounce_ms,
        )
        logger.info("Button service started on pin %d (BOARD)", self._pin)

    async def stop(self) -> None:
        """Clean up GPIO."""
        if self._gpio:
            self._gpio.remove_event_detect(self._pin)
            self._gpio.cleanup(self._pin)
            logger.info("Button service stopped")

    async def wait_gesture(self) -> ButtonEvent:
        assert self._state_machine is not None, "Call start() first"
        return await self._state_machine.wait_gesture()

    def subscribe(self) -> AsyncIterator[ButtonEvent]:
        assert self._state_machine is not None, "Call start() first"
        return self._state_machine.subscribe()

    def _gpio_callback(self, channel: int) -> None:
        """GPIO edge callback — runs in RPi.GPIO background thread."""
        if self._gpio is None or self._state_machine is None:
            return
        state = self._gpio.input(self._pin)
        if state:
            self._state_machine.on_press()
        else:
            self._state_machine.on_release()
