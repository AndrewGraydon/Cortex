"""RGB565 pixel format conversion for ST7789 LCD.

Converts Pillow RGB images to the 16-bit RGB565 format expected by the
ST7789 display controller (big-endian byte order).

RGB565 packing: RRRRRGGGGGGBBBBB (5-6-5 bits)
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from PIL import Image


def pillow_to_rgb565(image: Image.Image) -> bytes:
    """Convert a Pillow image to RGB565 big-endian bytes.

    Args:
        image: Any Pillow image (auto-converted to RGB).

    Returns:
        Raw bytes in RGB565 big-endian format, suitable for SPI
        transfer to ST7789. Length = width * height * 2.
    """
    rgb: NDArray[np.uint8] = np.array(image.convert("RGB"))
    r = (rgb[:, :, 0] >> 3).astype(np.uint16)
    g = (rgb[:, :, 1] >> 2).astype(np.uint16)
    b = (rgb[:, :, 2] >> 3).astype(np.uint16)
    rgb565 = (r << 11) | (g << 5) | b
    # Big-endian: high byte first
    high = (rgb565 >> 8).astype(np.uint8)
    low = (rgb565 & 0xFF).astype(np.uint8)
    return np.dstack((high, low)).flatten().tobytes()


def rgb565_frame_size(width: int, height: int) -> int:
    """Return the byte count for an RGB565 frame of given dimensions."""
    return width * height * 2
