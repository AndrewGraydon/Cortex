"""Tests for RGB565 pixel format conversion."""

from __future__ import annotations

import numpy as np
from PIL import Image

from cortex.hal.display.rgb565 import pillow_to_rgb565, rgb565_frame_size


class TestRgb565Conversion:
    """Verify RGB → RGB565 big-endian packing."""

    def test_pure_black(self) -> None:
        img = Image.new("RGB", (1, 1), (0, 0, 0))
        data = pillow_to_rgb565(img)
        assert data == b"\x00\x00"

    def test_pure_white(self) -> None:
        img = Image.new("RGB", (1, 1), (255, 255, 255))
        data = pillow_to_rgb565(img)
        # R=31, G=63, B=31 → 0xFFFF
        assert data == b"\xFF\xFF"

    def test_pure_red(self) -> None:
        img = Image.new("RGB", (1, 1), (255, 0, 0))
        data = pillow_to_rgb565(img)
        # R=31, G=0, B=0 → 11111_000000_00000 = 0xF800
        assert data == b"\xF8\x00"

    def test_pure_green(self) -> None:
        img = Image.new("RGB", (1, 1), (0, 255, 0))
        data = pillow_to_rgb565(img)
        # R=0, G=63, B=0 → 00000_111111_00000 = 0x07E0
        assert data == b"\x07\xE0"

    def test_pure_blue(self) -> None:
        img = Image.new("RGB", (1, 1), (0, 0, 255))
        data = pillow_to_rgb565(img)
        # R=0, G=0, B=31 → 00000_000000_11111 = 0x001F
        assert data == b"\x00\x1F"

    def test_lcd_frame_size(self) -> None:
        """240×280 LCD produces 134,400 bytes."""
        img = Image.new("RGB", (240, 280), (0, 0, 0))
        data = pillow_to_rgb565(img)
        assert len(data) == 134_400

    def test_frame_size_helper(self) -> None:
        assert rgb565_frame_size(240, 280) == 134_400
        assert rgb565_frame_size(1, 1) == 2

    def test_rgba_input_converted(self) -> None:
        """RGBA images are auto-converted to RGB."""
        img = Image.new("RGBA", (2, 2), (255, 0, 0, 128))
        data = pillow_to_rgb565(img)
        assert len(data) == 8  # 2×2×2
        # Alpha is discarded — should be pure red
        assert data[:2] == b"\xF8\x00"

    def test_grayscale_input_converted(self) -> None:
        """Grayscale images are auto-converted to RGB."""
        img = Image.new("L", (1, 1), 128)
        data = pillow_to_rgb565(img)
        assert len(data) == 2

    def test_known_color_mid_gray(self) -> None:
        """Mid-gray (128, 128, 128) maps to expected RGB565 value."""
        img = Image.new("RGB", (1, 1), (128, 128, 128))
        data = pillow_to_rgb565(img)
        # R=128>>3=16, G=128>>2=32, B=128>>3=16
        # 10000_100000_10000 = 0x8410
        assert data == b"\x84\x10"

    def test_output_is_bytes(self) -> None:
        img = Image.new("RGB", (4, 4), (100, 150, 200))
        data = pillow_to_rgb565(img)
        assert isinstance(data, bytes)
        assert len(data) == 32  # 4×4×2

    def test_pixel_order_preserved(self) -> None:
        """Pixels are output in row-major order (left→right, top→bottom)."""
        img = Image.new("RGB", (2, 1))
        img.putpixel((0, 0), (255, 0, 0))  # red
        img.putpixel((1, 0), (0, 0, 255))  # blue
        data = pillow_to_rgb565(img)
        assert data[:2] == b"\xF8\x00"  # red
        assert data[2:4] == b"\x00\x1F"  # blue

    def test_large_image_performance(self) -> None:
        """240×280 conversion completes without error."""
        arr = np.random.randint(0, 256, (280, 240, 3), dtype=np.uint8)
        img = Image.fromarray(arr, "RGB")
        data = pillow_to_rgb565(img)
        assert len(data) == 134_400
