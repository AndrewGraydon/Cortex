"""Async render loop — drives the LCD at up to 30 FPS.

Uses dirty-flag optimization: static states (IDLE, ERROR) render
once then sleep; animated states (LISTENING, THINKING, SPEAKING,
ALERT) run at full framerate.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any, Protocol

from PIL import Image

from cortex.hal.display.renderer import FrameRenderer
from cortex.hal.display.rgb565 import pillow_to_rgb565
from cortex.hal.types import DisplayState

logger = logging.getLogger(__name__)

# Target frame interval (30 FPS)
_FRAME_INTERVAL_S = 1.0 / 30.0

# Idle re-render interval (clock update)
_IDLE_REFRESH_S = 60.0

# Speaking auto-scroll speed: pixels per frame at 30 FPS (~30 px/s)
_SCROLL_PX_PER_FRAME = 1

# Animated states that require continuous rendering
_ANIMATED_STATES = {
    DisplayState.LISTENING,
    DisplayState.THINKING,
    DisplayState.SPEAKING,
    DisplayState.ALERT,
}


class DisplayDriver(Protocol):
    """Protocol for hardware display drivers (ST7789, mock, etc.)."""

    def write_frame(self, data: bytes) -> None:
        """Write raw RGB565 frame data to the display."""
        ...


class RenderLoop:
    """Async render loop driving the LCD display.

    Features:
    - Dirty-flag optimization: only re-renders when state/text changes
    - Static states (IDLE, ERROR) render once then sleep
    - Animated states run at 30 FPS
    - Auto-scroll for SPEAKING state
    """

    def __init__(
        self,
        renderer: FrameRenderer,
        driver: DisplayDriver | None = None,
    ) -> None:
        self._renderer = renderer
        self._driver = driver
        self._state = DisplayState.IDLE
        self._text = ""
        self._dirty = True
        self._frame_num = 0
        self._scroll_offset = 0
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._last_frame: Image.Image | None = None
        self._on_frame: list[Any] = []  # callbacks for testing

    @property
    def state(self) -> DisplayState:
        return self._state

    @property
    def text(self) -> str:
        return self._text

    @property
    def frame_num(self) -> int:
        return self._frame_num

    @property
    def scroll_offset(self) -> int:
        return self._scroll_offset

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def last_frame(self) -> Image.Image | None:
        """Last rendered frame (for testing/debugging)."""
        return self._last_frame

    def set_state(self, state: DisplayState) -> None:
        """Update display state and mark dirty."""
        if state != self._state:
            self._state = state
            self._dirty = True
            self._frame_num = 0
            self._scroll_offset = 0
            self._renderer.clear_cache()
            logger.debug("Render state: %s", state.value)

    def set_text(self, text: str) -> None:
        """Update display text and mark dirty."""
        if text != self._text:
            self._text = text
            self._dirty = True

    def on_frame(self, callback: Any) -> None:
        """Register a callback fired after each frame render."""
        self._on_frame.append(callback)

    async def start(self) -> None:
        """Start the render loop."""
        if self._running:
            return
        self._running = True
        self._dirty = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Render loop started")

    async def stop(self) -> None:
        """Stop the render loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("Render loop stopped")

    def _is_animated(self) -> bool:
        """Whether the current state requires continuous rendering."""
        return self._state in _ANIMATED_STATES

    async def _loop(self) -> None:
        """Main render loop."""
        last_idle_render = 0.0

        while self._running:
            now = time.monotonic()
            should_render = False

            if self._is_animated():
                should_render = True
                if self._state == DisplayState.SPEAKING:
                    self._scroll_offset += _SCROLL_PX_PER_FRAME
            elif self._dirty or (
                self._state == DisplayState.IDLE
                and (now - last_idle_render) >= _IDLE_REFRESH_S
            ):
                should_render = True

            if should_render:
                self._render_frame()
                self._dirty = False
                if self._state == DisplayState.IDLE:
                    last_idle_render = now

            # Sleep until next frame
            elapsed = time.monotonic() - now
            sleep_time = max(0, _FRAME_INTERVAL_S - elapsed)
            await asyncio.sleep(sleep_time)

    def _render_frame(self) -> None:
        """Render one frame and send to driver."""
        img = self._renderer.render(
            state=self._state,
            text=self._text,
            frame_num=self._frame_num,
            scroll_offset=self._scroll_offset,
        )
        self._last_frame = img
        self._frame_num += 1

        # Send to hardware driver if available
        if self._driver:
            data = pillow_to_rgb565(img)
            self._driver.write_frame(data)

        # Fire callbacks
        for cb in self._on_frame:
            cb(img)
