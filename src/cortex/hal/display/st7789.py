"""ST7789 LCD driver — SPI interface for 240×280 IPS display.

Hardware: Whisplay HAT ST7789 LCD connected via SPI0.
  - DC (Data/Command): Pin 13 (BOARD)
  - RST (Reset): Pin 7 (BOARD)
  - SPI: Bus 0, Device 0, 100 MHz, Mode 0
  - Y-axis offset: +20 pixels for 240×280 panel variant

Pi-only — requires spidev and RPi.GPIO packages.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# GPIO pins (BOARD numbering)
PIN_DC = 13   # Data/Command select
PIN_RST = 7   # Hardware reset

# SPI configuration
SPI_BUS = 0
SPI_DEVICE = 0
SPI_SPEED_HZ = 100_000_000  # 100 MHz
SPI_MODE = 0

# Display dimensions
DISPLAY_WIDTH = 240
DISPLAY_HEIGHT = 280
Y_OFFSET = 20  # 240×280 panel variant offset

# ST7789 commands
_CMD_SLPOUT = 0x11
_CMD_MADCTL = 0x36
_CMD_COLMOD = 0x3A
_CMD_INVON = 0xBB
_CMD_DISPON = 0x29
_CMD_CASET = 0x2A
_CMD_RASET = 0x2B
_CMD_RAMWR = 0x2C

# Maximum SPI transfer chunk size
_SPI_CHUNK_SIZE = 4096


class ST7789Driver:
    """SPI driver for ST7789 240×280 LCD.

    Pi-only — requires spidev and RPi.GPIO.
    Implements the DisplayDriver protocol from render_loop.
    """

    def __init__(self) -> None:
        self._spi: Any = None
        self._gpio: Any = None

    def start(self) -> None:
        """Initialize SPI bus and GPIO pins, then run LCD init sequence."""
        try:
            import RPi.GPIO as GPIO  # type: ignore[import-untyped]
            import spidev
        except ImportError as e:
            msg = "spidev/RPi.GPIO not available — not running on Pi?"
            raise RuntimeError(msg) from e

        self._gpio = GPIO
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(PIN_DC, GPIO.OUT)
        GPIO.setup(PIN_RST, GPIO.OUT)

        self._spi = spidev.SpiDev()
        self._spi.open(SPI_BUS, SPI_DEVICE)
        self._spi.max_speed_hz = SPI_SPEED_HZ
        self._spi.mode = SPI_MODE

        self._hardware_reset()
        self._init_sequence()

        logger.info(
            "ST7789 driver started (%dx%d, SPI %dMHz)",
            DISPLAY_WIDTH, DISPLAY_HEIGHT, SPI_SPEED_HZ // 1_000_000,
        )

    def stop(self) -> None:
        """Clean up SPI and GPIO resources."""
        if self._spi:
            self._spi.close()
            self._spi = None
        if self._gpio:
            self._gpio.cleanup(PIN_DC)
            self._gpio.cleanup(PIN_RST)
            self._gpio = None
        logger.info("ST7789 driver stopped")

    def write_frame(self, data: bytes) -> None:
        """Write a full frame of RGB565 data to the display.

        Args:
            data: Raw RGB565 bytes (240 × 280 × 2 = 134,400 bytes).
        """
        self._set_window(0, 0, DISPLAY_WIDTH - 1, DISPLAY_HEIGHT - 1)
        self._write_command(_CMD_RAMWR)
        self._write_data(data)

    def fill(self, color_rgb565: int) -> None:
        """Fill the entire display with a single RGB565 color."""
        high = (color_rgb565 >> 8) & 0xFF
        low = color_rgb565 & 0xFF
        data = bytes([high, low]) * (DISPLAY_WIDTH * DISPLAY_HEIGHT)
        self.write_frame(data)

    def _hardware_reset(self) -> None:
        """Toggle RST pin for hardware reset."""
        gpio = self._gpio
        gpio.output(PIN_RST, gpio.HIGH)
        time.sleep(0.1)
        gpio.output(PIN_RST, gpio.LOW)
        time.sleep(0.1)
        gpio.output(PIN_RST, gpio.HIGH)
        time.sleep(0.12)

    def _init_sequence(self) -> None:
        """Run the ST7789 initialization command sequence."""
        # Sleep out
        self._write_command(_CMD_SLPOUT)
        time.sleep(0.12)

        # Memory access control — top-to-bottom, left-to-right, RGB
        self._write_command(_CMD_MADCTL)
        self._write_data(bytes([0x00]))

        # Color mode: 16-bit RGB565
        self._write_command(_CMD_COLMOD)
        self._write_data(bytes([0x55]))

        # Inversion on (required for IPS panels)
        self._write_command(_CMD_INVON)
        time.sleep(0.01)

        # Display on
        self._write_command(_CMD_DISPON)
        time.sleep(0.1)

    def _set_window(self, x0: int, y0: int, x1: int, y1: int) -> None:
        """Set the drawing window (column/row address)."""
        # Apply Y offset for 240×280 panel
        y0 += Y_OFFSET
        y1 += Y_OFFSET

        # Column address set
        self._write_command(_CMD_CASET)
        self._write_data(bytes([
            (x0 >> 8) & 0xFF, x0 & 0xFF,
            (x1 >> 8) & 0xFF, x1 & 0xFF,
        ]))

        # Row address set
        self._write_command(_CMD_RASET)
        self._write_data(bytes([
            (y0 >> 8) & 0xFF, y0 & 0xFF,
            (y1 >> 8) & 0xFF, y1 & 0xFF,
        ]))

    def _write_command(self, cmd: int) -> None:
        """Write a command byte (DC=LOW)."""
        self._gpio.output(PIN_DC, self._gpio.LOW)
        self._spi.writebytes([cmd])

    def _write_data(self, data: bytes) -> None:
        """Write data bytes (DC=HIGH), chunked for SPI buffer limits."""
        self._gpio.output(PIN_DC, self._gpio.HIGH)
        # Write in chunks to avoid SPI buffer overflow
        for offset in range(0, len(data), _SPI_CHUNK_SIZE):
            chunk = data[offset:offset + _SPI_CHUNK_SIZE]
            self._spi.writebytes2(chunk)
