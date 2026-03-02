"""Display service — LCD screen states and LED coordination.

Hardware: ST7789 240×280 SPI LCD on Whisplay HAT.
Renders using Pillow. Phase 1 screens are simple text-based:
  - Idle: "Cortex" centered
  - Listening: "Listening..." with green border
  - Thinking: "Thinking..." with orange border
  - Speaking: Response text with blue border, scrolling
  - Alert/Error: Message with red border

LED colors coordinated with display states.
"""

from __future__ import annotations

import logging
from typing import Any

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

    Uses ST7789 SPI LCD via spidev + Pillow rendering.
    Pi-only — requires spidev and RPi.GPIO.
    """

    def __init__(self) -> None:
        self._state = DisplayState.IDLE
        self._current_text = ""
        self._spi: Any = None
        self._gpio: Any = None
        self._led: Any = None

    async def start(self, led_controller: Any = None) -> None:
        """Initialize SPI display and optional LED controller."""
        self._led = led_controller
        # SPI initialization would go here (Pi-only)
        # For Phase 1, we log the state transitions
        logger.info("Display service started (%dx%d)", LCD_WIDTH, LCD_HEIGHT)

    async def stop(self) -> None:
        """Clean up display resources."""
        logger.info("Display service stopped")

    async def set_state(self, state: DisplayState, text: str = "") -> None:
        """Update display to show the given state."""
        prev = self._state
        self._state = state
        self._current_text = text

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

    async def get_state(self) -> DisplayState:
        """Get current display state."""
        return self._state
