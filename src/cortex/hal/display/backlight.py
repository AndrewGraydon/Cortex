"""Backlight controller for Whisplay HAT LCD.

Hardware: Active-low backlight on GPIO pin 15 (BOARD).
PWM at 1kHz, same pattern as GpioLedController.

Pi-only — requires RPi.GPIO.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# BOARD pin number for backlight control
BACKLIGHT_PIN = 15
PWM_FREQUENCY = 1000  # 1kHz


class BacklightController:
    """LCD backlight control via GPIO PWM.

    Active-low: duty_cycle = 100 - brightness.
    Pi-only — requires RPi.GPIO.
    """

    def __init__(self) -> None:
        self._gpio: Any = None
        self._pwm: Any = None
        self._brightness = 0

    @property
    def brightness(self) -> int:
        """Current brightness (0-100)."""
        return self._brightness

    def start(self, initial_brightness: int = 80) -> None:
        """Initialize GPIO PWM and set initial brightness."""
        try:
            import RPi.GPIO as GPIO  # type: ignore[import-untyped]
        except ImportError as e:
            msg = "RPi.GPIO not available — not running on Pi?"
            raise RuntimeError(msg) from e

        self._gpio = GPIO
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(BACKLIGHT_PIN, GPIO.OUT)

        self._pwm = GPIO.PWM(BACKLIGHT_PIN, PWM_FREQUENCY)
        # Active-low: 100 - brightness
        self._brightness = initial_brightness
        self._pwm.start(100 - initial_brightness)

        logger.info("Backlight started (pin %d, %d%%)", BACKLIGHT_PIN, initial_brightness)

    def stop(self) -> None:
        """Turn off backlight and clean up."""
        if self._pwm:
            self._pwm.stop()
        if self._gpio:
            self._gpio.cleanup(BACKLIGHT_PIN)
        self._brightness = 0
        logger.info("Backlight stopped")

    def set_brightness(self, brightness: int) -> None:
        """Set backlight brightness (0-100).

        Args:
            brightness: 0 = off, 100 = full brightness.
        """
        brightness = max(0, min(100, brightness))
        self._brightness = brightness
        if self._pwm:
            self._pwm.ChangeDutyCycle(100 - brightness)
