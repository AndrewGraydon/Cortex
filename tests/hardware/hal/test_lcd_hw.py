"""Hardware tests for ST7789 LCD display.

Run on Pi only: pytest tests/hardware/hal/test_lcd_hw.py -m hardware -v

Tests SPI initialization, screen fill, all display modes, backlight,
and visual verification of rendering pipeline.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from PIL import Image

from cortex.hal.display.backlight import BacklightController
from cortex.hal.display.render_loop import RenderLoop
from cortex.hal.display.renderer import LCD_HEIGHT, LCD_WIDTH, FrameRenderer
from cortex.hal.display.rgb565 import pillow_to_rgb565
from cortex.hal.display.st7789 import ST7789Driver
from cortex.hal.types import DisplayState

pytestmark = pytest.mark.hardware


@pytest.fixture(scope="module")
def driver() -> ST7789Driver:
    """Initialize ST7789 driver for the test module."""
    drv = ST7789Driver()
    drv.start()
    yield drv
    drv.stop()


@pytest.fixture(scope="module")
def backlight() -> BacklightController:
    """Initialize backlight controller for the test module."""
    bl = BacklightController()
    bl.start(initial_brightness=80)
    yield bl
    bl.stop()


class TestST7789Init:
    """SPI and display initialization."""

    def test_driver_starts(self, driver: ST7789Driver) -> None:
        """Driver initializes without error."""
        assert driver._spi is not None

    def test_fill_black(self, driver: ST7789Driver) -> None:
        """Fill screen with black."""
        driver.fill(0x0000)
        time.sleep(0.5)

    def test_fill_red(self, driver: ST7789Driver) -> None:
        """Fill screen with red (RGB565: 0xF800)."""
        driver.fill(0xF800)
        time.sleep(0.5)

    def test_fill_green(self, driver: ST7789Driver) -> None:
        """Fill screen with green (RGB565: 0x07E0)."""
        driver.fill(0x07E0)
        time.sleep(0.5)

    def test_fill_blue(self, driver: ST7789Driver) -> None:
        """Fill screen with blue (RGB565: 0x001F)."""
        driver.fill(0x001F)
        time.sleep(0.5)

    def test_fill_white(self, driver: ST7789Driver) -> None:
        """Fill screen with white."""
        driver.fill(0xFFFF)
        time.sleep(0.5)


class TestFrameWrite:
    """Full frame rendering via Pillow → RGB565 → SPI."""

    def test_pillow_frame(self, driver: ST7789Driver) -> None:
        """Render a Pillow image and send to display."""
        img = Image.new("RGB", (LCD_WIDTH, LCD_HEIGHT), (0, 0, 0))
        from PIL import ImageDraw

        draw = ImageDraw.Draw(img)
        draw.rectangle([20, 20, 220, 260], outline=(255, 255, 255), width=2)
        draw.text((60, 130), "Cortex", fill=(255, 255, 255))
        data = pillow_to_rgb565(img)
        driver.write_frame(data)
        time.sleep(1)


class TestAllDisplayModes:
    """Walk through all 6 display states."""

    def test_idle_mode(self, driver: ST7789Driver) -> None:
        renderer = FrameRenderer()
        img = renderer.render(DisplayState.IDLE)
        driver.write_frame(pillow_to_rgb565(img))
        time.sleep(1)

    def test_listening_mode(self, driver: ST7789Driver) -> None:
        renderer = FrameRenderer()
        img = renderer.render(DisplayState.LISTENING, frame_num=5)
        driver.write_frame(pillow_to_rgb565(img))
        time.sleep(1)

    def test_thinking_mode(self, driver: ST7789Driver) -> None:
        renderer = FrameRenderer()
        img = renderer.render(DisplayState.THINKING, frame_num=15)
        driver.write_frame(pillow_to_rgb565(img))
        time.sleep(1)

    def test_speaking_mode(self, driver: ST7789Driver) -> None:
        renderer = FrameRenderer()
        img = renderer.render(
            DisplayState.SPEAKING,
            text="Hello! I'm Cortex, your local AI assistant. How can I help you today?",
        )
        driver.write_frame(pillow_to_rgb565(img))
        time.sleep(1)

    def test_alert_mode(self, driver: ST7789Driver) -> None:
        renderer = FrameRenderer()
        img = renderer.render(DisplayState.ALERT, text="Set a timer for 5 minutes?")
        driver.write_frame(pillow_to_rgb565(img))
        time.sleep(1)

    def test_error_mode(self, driver: ST7789Driver) -> None:
        renderer = FrameRenderer()
        img = renderer.render(DisplayState.ERROR, text="NPU temperature critical")
        driver.write_frame(pillow_to_rgb565(img))
        time.sleep(1)


class TestBacklight:
    """Backlight brightness control."""

    def test_brightness_100(self, backlight: BacklightController) -> None:
        backlight.set_brightness(100)
        assert backlight.brightness == 100
        time.sleep(0.5)

    def test_brightness_50(self, backlight: BacklightController) -> None:
        backlight.set_brightness(50)
        assert backlight.brightness == 50
        time.sleep(0.5)

    def test_brightness_0(self, backlight: BacklightController) -> None:
        backlight.set_brightness(0)
        assert backlight.brightness == 0
        time.sleep(0.5)

    def test_brightness_restored(self, backlight: BacklightController) -> None:
        backlight.set_brightness(80)
        assert backlight.brightness == 80


class TestRenderLoopHw:
    """Render loop with real hardware driver."""

    async def test_animated_listening(self, driver: ST7789Driver) -> None:
        """Run 2 seconds of animated listening mode."""
        renderer = FrameRenderer()
        loop = RenderLoop(renderer=renderer, driver=driver)
        loop.set_state(DisplayState.LISTENING)
        await loop.start()
        await asyncio.sleep(2)
        await loop.stop()
        assert loop.frame_num > 30  # At least 1 second of frames

    async def test_state_transitions(self, driver: ST7789Driver) -> None:
        """Walk through states with render loop."""
        renderer = FrameRenderer()
        loop = RenderLoop(renderer=renderer, driver=driver)
        await loop.start()

        for state in DisplayState:
            loop.set_state(state)
            if state == DisplayState.SPEAKING:
                loop.set_text("Transitioning through display states...")
            elif state == DisplayState.ALERT:
                loop.set_text("Action approval needed")
            elif state == DisplayState.ERROR:
                loop.set_text("Test error message")
            await asyncio.sleep(1)

        await loop.stop()
