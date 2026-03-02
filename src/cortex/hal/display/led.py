"""RGB LED control via PWM.

Hardware: Active-low RGB LED on Whisplay HAT.
  - Red: Pin 22 (BOARD)
  - Green: Pin 18 (BOARD)
  - Blue: Pin 16 (BOARD)

Active-low means duty_cycle=100 is OFF, duty_cycle=0 is full brightness.
"""

from __future__ import annotations

import logging
from typing import Any

from cortex.hal.types import LedColor

logger = logging.getLogger(__name__)

# BOARD pin numbers for RGB LED (active-low)
LED_PIN_RED = 22
LED_PIN_GREEN = 18
LED_PIN_BLUE = 16
PWM_FREQUENCY = 1000  # 1kHz PWM


class GpioLedController:
    """RGB LED control via RPi.GPIO PWM.

    Pi-only — requires RPi.GPIO package.
    """

    def __init__(self) -> None:
        self._gpio: Any = None
        self._pwm_r: Any = None
        self._pwm_g: Any = None
        self._pwm_b: Any = None
        self._current_color = LedColor.off()

    async def start(self) -> None:
        """Initialize GPIO pins and PWM channels."""
        try:
            import RPi.GPIO as GPIO  # type: ignore[import-untyped]
        except ImportError as e:
            msg = "RPi.GPIO not available — not running on Pi?"
            raise RuntimeError(msg) from e

        self._gpio = GPIO
        GPIO.setmode(GPIO.BOARD)

        for pin in [LED_PIN_RED, LED_PIN_GREEN, LED_PIN_BLUE]:
            GPIO.setup(pin, GPIO.OUT)

        self._pwm_r = GPIO.PWM(LED_PIN_RED, PWM_FREQUENCY)
        self._pwm_g = GPIO.PWM(LED_PIN_GREEN, PWM_FREQUENCY)
        self._pwm_b = GPIO.PWM(LED_PIN_BLUE, PWM_FREQUENCY)

        # Start with LEDs off (100% duty = off for active-low)
        self._pwm_r.start(100)
        self._pwm_g.start(100)
        self._pwm_b.start(100)

        pins = f"{LED_PIN_RED}/{LED_PIN_GREEN}/{LED_PIN_BLUE}"
        logger.info("LED controller started (pins %s)", pins)

    async def stop(self) -> None:
        """Turn off LEDs and clean up."""
        for pwm in [self._pwm_r, self._pwm_g, self._pwm_b]:
            if pwm:
                pwm.stop()
        if self._gpio:
            for pin in [LED_PIN_RED, LED_PIN_GREEN, LED_PIN_BLUE]:
                self._gpio.cleanup(pin)
        logger.info("LED controller stopped")

    async def set_color(self, color: LedColor) -> None:
        """Set RGB LED color.

        Values 0-255 per channel. Active-low conversion applied internally.
        """
        self._current_color = color
        if self._pwm_r:
            # Active-low: 0 brightness = 100% duty, 255 brightness = 0% duty
            self._pwm_r.ChangeDutyCycle(100 - (color.r / 255 * 100))
            self._pwm_g.ChangeDutyCycle(100 - (color.g / 255 * 100))
            self._pwm_b.ChangeDutyCycle(100 - (color.b / 255 * 100))

    @property
    def current_color(self) -> LedColor:
        return self._current_color
