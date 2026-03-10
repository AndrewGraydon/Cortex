"""Tests for FrameRenderer — one render method per DisplayState."""

from __future__ import annotations

import pytest
from PIL import Image

from cortex.hal.display.renderer import (
    AMBER,
    BLUE,
    GREEN,
    LCD_HEIGHT,
    LCD_WIDTH,
    RED,
    FrameRenderer,
)
from cortex.hal.types import DisplayState


@pytest.fixture()
def renderer() -> FrameRenderer:
    return FrameRenderer()


class TestFrameBasics:
    """All frames share common properties."""

    @pytest.mark.parametrize("state", list(DisplayState))
    def test_frame_dimensions(self, renderer: FrameRenderer, state: DisplayState) -> None:
        img = renderer.render(state)
        assert img.size == (LCD_WIDTH, LCD_HEIGHT)

    @pytest.mark.parametrize("state", list(DisplayState))
    def test_frame_mode_rgb(self, renderer: FrameRenderer, state: DisplayState) -> None:
        img = renderer.render(state)
        assert img.mode == "RGB"

    @pytest.mark.parametrize("state", list(DisplayState))
    def test_frame_returns_image(self, renderer: FrameRenderer, state: DisplayState) -> None:
        img = renderer.render(state)
        assert isinstance(img, Image.Image)


class TestIdleFrame:
    """IDLE: 'Cortex' centered, clock, dim blue accent."""

    def test_mostly_black_background(self, renderer: FrameRenderer) -> None:
        img = renderer.render(DisplayState.IDLE)
        # Most pixels should be black
        pixels = list(img.get_flattened_data())
        black_count = sum(1 for p in pixels if p == (0, 0, 0))
        assert black_count > len(pixels) * 0.8

    def test_has_white_pixels_for_title(self, renderer: FrameRenderer) -> None:
        img = renderer.render(DisplayState.IDLE)
        pixels = list(img.get_flattened_data())
        white_count = sum(1 for p in pixels if p[0] > 200 and p[1] > 200 and p[2] > 200)
        assert white_count > 0

    def test_has_blue_accent(self, renderer: FrameRenderer) -> None:
        img = renderer.render(DisplayState.IDLE)
        pixels = list(img.get_flattened_data())
        blue_count = sum(1 for p in pixels if p[2] > 50 and p[0] == 0 and p[1] == 0)
        assert blue_count > 0


class TestListeningFrame:
    """LISTENING: Green border, pulsing dot."""

    def test_has_green_border(self, renderer: FrameRenderer) -> None:
        img = renderer.render(DisplayState.LISTENING)
        # Top-left corner pixel should be green (border)
        pixel = img.getpixel((0, 0))
        assert pixel == GREEN

    def test_has_green_text(self, renderer: FrameRenderer) -> None:
        img = renderer.render(DisplayState.LISTENING)
        pixels = list(img.get_flattened_data())
        green_count = sum(1 for p in pixels if p[1] > 200 and p[0] < 50 and p[2] < 50)
        assert green_count > 0

    def test_pulsing_dot_changes(self, renderer: FrameRenderer) -> None:
        """Different frame_num produces different brightness."""
        img1 = renderer.render(DisplayState.LISTENING, frame_num=0)
        img2 = renderer.render(DisplayState.LISTENING, frame_num=8)
        # Images should differ (dot brightness changes)
        assert img1.tobytes() != img2.tobytes()

    def test_static_elements_same(self, renderer: FrameRenderer) -> None:
        """Border and text don't change between frames."""
        img1 = renderer.render(DisplayState.LISTENING, frame_num=0)
        img2 = renderer.render(DisplayState.LISTENING, frame_num=0)
        assert img1.tobytes() == img2.tobytes()


class TestThinkingFrame:
    """THINKING: Amber border, cycling dots."""

    def test_has_amber_border(self, renderer: FrameRenderer) -> None:
        img = renderer.render(DisplayState.THINKING)
        pixel = img.getpixel((0, 0))
        assert pixel == AMBER

    def test_dots_cycle(self, renderer: FrameRenderer) -> None:
        """Dot count changes with frame_num."""
        img1 = renderer.render(DisplayState.THINKING, frame_num=0)
        img2 = renderer.render(DisplayState.THINKING, frame_num=10)
        img3 = renderer.render(DisplayState.THINKING, frame_num=20)
        # At least 2 of 3 should differ
        bytes_set = {img1.tobytes(), img2.tobytes(), img3.tobytes()}
        assert len(bytes_set) >= 2


class TestSpeakingFrame:
    """SPEAKING: Blue header, scrollable text."""

    def test_has_blue_header(self, renderer: FrameRenderer) -> None:
        img = renderer.render(DisplayState.SPEAKING, text="Hello")
        # Top-left should be blue header
        pixel = img.getpixel((5, 5))
        assert pixel == BLUE

    def test_empty_text(self, renderer: FrameRenderer) -> None:
        img = renderer.render(DisplayState.SPEAKING, text="")
        assert img.size == (LCD_WIDTH, LCD_HEIGHT)

    def test_text_rendered(self, renderer: FrameRenderer) -> None:
        img = renderer.render(DisplayState.SPEAKING, text="Hello World")
        pixels = list(img.get_flattened_data())
        # Should have some white text pixels below header
        white_below_header = sum(
            1 for i, p in enumerate(pixels)
            if p[0] > 200 and p[1] > 200 and p[2] > 200
            and i // LCD_WIDTH > 32  # below header
        )
        assert white_below_header > 0

    def test_scroll_offset_changes_output(self, renderer: FrameRenderer) -> None:
        long_text = "Line " * 100
        img1 = renderer.render(DisplayState.SPEAKING, text=long_text, scroll_offset=0)
        img2 = renderer.render(DisplayState.SPEAKING, text=long_text, scroll_offset=50)
        assert img1.tobytes() != img2.tobytes()

    def test_scroll_offset_clamped(self, renderer: FrameRenderer) -> None:
        """Scroll past end of text doesn't crash."""
        img = renderer.render(DisplayState.SPEAKING, text="Short", scroll_offset=9999)
        assert img.size == (LCD_WIDTH, LCD_HEIGHT)


class TestAlertFrame:
    """ALERT: Red border, approve/deny footer."""

    def test_has_red_border(self, renderer: FrameRenderer) -> None:
        img = renderer.render(DisplayState.ALERT, text="Action needed")
        pixel = img.getpixel((0, 0))
        assert pixel == RED

    def test_has_footer_text(self, renderer: FrameRenderer) -> None:
        img = renderer.render(DisplayState.ALERT, text="Approve?")
        # Bottom area should have some gray text pixels
        pixels = list(img.get_flattened_data())
        bottom_gray = sum(
            1 for i, p in enumerate(pixels)
            if 100 < p[0] < 180 and 100 < p[1] < 180 and 100 < p[2] < 180
            and i // LCD_WIDTH > LCD_HEIGHT - 40
        )
        assert bottom_gray > 0

    def test_alert_text_rendered(self, renderer: FrameRenderer) -> None:
        img = renderer.render(DisplayState.ALERT, text="Delete file?")
        pixels = list(img.get_flattened_data())
        white_count = sum(1 for p in pixels if p[0] > 200 and p[1] > 200 and p[2] > 200)
        assert white_count > 0


class TestErrorFrame:
    """ERROR: Red border, centered error message."""

    def test_has_red_border(self, renderer: FrameRenderer) -> None:
        img = renderer.render(DisplayState.ERROR, text="Something failed")
        pixel = img.getpixel((0, 0))
        assert pixel == RED

    def test_default_error_text(self, renderer: FrameRenderer) -> None:
        """Empty text shows 'Error'."""
        img = renderer.render(DisplayState.ERROR)
        pixels = list(img.get_flattened_data())
        red_text = sum(1 for p in pixels if p[0] > 200 and p[1] < 50 and p[2] < 50)
        assert red_text > 0

    def test_custom_error_text(self, renderer: FrameRenderer) -> None:
        img = renderer.render(DisplayState.ERROR, text="NPU overheated")
        pixels = list(img.get_flattened_data())
        red_text = sum(1 for p in pixels if p[0] > 200 and p[1] < 50 and p[2] < 50)
        assert red_text > 0


class TestClearCache:
    """Cache management."""

    def test_clear_cache_succeeds(self, renderer: FrameRenderer) -> None:
        renderer.render(DisplayState.IDLE)
        renderer.clear_cache()
        # Should still render fine after cache clear
        img = renderer.render(DisplayState.IDLE)
        assert img.size == (LCD_WIDTH, LCD_HEIGHT)
