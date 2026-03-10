"""Display service — LCD rendering + LED coordination.

Hardware: ST7789 240×280 SPI LCD on Whisplay HAT.
Renders using Pillow via FrameRenderer → RenderLoop → ST7789Driver.
  - Idle: "Cortex" centered with clock
  - Listening: green border, pulsing dot
  - Thinking: amber border, cycling dots
  - Speaking: blue header, scrollable response text
  - Alert: red border, approve/deny footer
  - Error: red border, centered message

LED colors coordinated with display states.
"""

from __future__ import annotations

import logging
from typing import Any

from cortex.hal.display.render_loop import RenderLoop
from cortex.hal.display.renderer import FrameRenderer
from cortex.hal.types import DisplayState, LedColor

logger = logging.getLogger(__name__)

# State → LED color mapping
STATE_LED_MAP: dict[DisplayState, LedColor] = {
    DisplayState.IDLE: LedColor.idle(),
    DisplayState.LISTENING: LedColor.listening(),
    DisplayState.THINKING: LedColor.thinking(),
    DisplayState.SPEAKING: LedColor.speaking(),
    DisplayState.ALERT: LedColor.error(),
    DisplayState.ERROR: LedColor.error(),
}

# LCD dimensions
LCD_WIDTH = 240
LCD_HEIGHT = 280


class WhisplayDisplayService:
    """LCD display service for Whisplay HAT.

    Wires together: ST7789Driver + BacklightController + FrameRenderer + RenderLoop.
    Falls back to software-only rendering when hardware is unavailable.
    """

    def __init__(self) -> None:
        self._state = DisplayState.IDLE
        self._current_text = ""
        self._led: Any = None
        self._driver: Any = None
        self._backlight: Any = None
        self._renderer = FrameRenderer()
        self._render_loop: RenderLoop | None = None

    async def start(self, led_controller: Any = None) -> None:
        """Initialize display pipeline and optional LED controller."""
        self._led = led_controller

        # Try to initialize hardware driver (Pi-only)
        driver = self._try_init_hardware()

        # Create and start render loop
        self._render_loop = RenderLoop(
            renderer=self._renderer,
            driver=driver,
        )
        await self._render_loop.start()
        logger.info("Display service started (%dx%d)", LCD_WIDTH, LCD_HEIGHT)

    def _try_init_hardware(self) -> Any:
        """Try to initialize ST7789 + backlight. Returns driver or None."""
        try:
            from cortex.hal.display.backlight import BacklightController
            from cortex.hal.display.st7789 import ST7789Driver

            driver = ST7789Driver()
            driver.start()
            self._driver = driver

            backlight = BacklightController()
            backlight.start(initial_brightness=80)
            self._backlight = backlight

            logger.info("Hardware display initialized")
            return driver
        except (ImportError, RuntimeError):
            logger.info("Hardware display unavailable — software rendering only")
            return None

    async def stop(self) -> None:
        """Clean up display resources."""
        if self._render_loop:
            await self._render_loop.stop()
            self._render_loop = None
        if self._backlight:
            self._backlight.stop()
            self._backlight = None
        if self._driver:
            self._driver.stop()
            self._driver = None
        logger.info("Display service stopped")

    async def set_state(self, state: DisplayState, text: str = "") -> None:
        """Update display to show the given state."""
        prev = self._state
        self._state = state
        self._current_text = text

        # Update render loop
        if self._render_loop:
            self._render_loop.set_state(state)
            if text:
                self._render_loop.set_text(text)

        # Update LED to match state
        if self._led:
            led_color = STATE_LED_MAP.get(state, LedColor.off())
            await self._led.set_color(led_color)

        if prev != state:
            logger.info("Display: %s → %s", prev.value, state.value)

    async def set_led(self, color: LedColor) -> None:
        """Set LED color directly (overrides state-based color)."""
        if self._led:
            await self._led.set_color(color)

    async def show_text(self, text: str, scroll: bool = False) -> None:
        """Show text on LCD (within current state frame)."""
        self._current_text = text
        if self._render_loop:
            self._render_loop.set_text(text)

    async def set_brightness(self, brightness: int) -> None:
        """Set LCD backlight brightness (0-100)."""
        if self._backlight:
            self._backlight.set_brightness(brightness)

    async def get_state(self) -> DisplayState:
        """Get current display state."""
        return self._state
