"""Text rendering for Whisplay LCD.

Font loading, word-level wrapping, and line-level image caching.
All rendering is pure Pillow — no hardware dependency.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from PIL.ImageFont import FreeTypeFont

logger = logging.getLogger(__name__)

# Default font: Pillow's built-in FreeType font (Pillow >= 10)
# Override by placing a .ttf file in the assets directory.
_ASSETS_DIR = Path(__file__).parent / "assets"
_BUNDLED_FONT = _ASSETS_DIR / "NotoSans-Regular.ttf"


@lru_cache(maxsize=16)
def get_font(size: int, bold: bool = False) -> FreeTypeFont:
    """Load a FreeType font at the given size.

    Tries bundled NotoSans first, falls back to Pillow default.
    Results are cached by (size, bold).
    """
    if _BUNDLED_FONT.exists():
        try:
            return ImageFont.truetype(str(_BUNDLED_FONT), size)
        except OSError:
            logger.warning("Failed to load bundled font, using default")
    font = ImageFont.load_default(size=size)
    assert isinstance(font, ImageFont.FreeTypeFont)
    return font


class TextRenderer:
    """Renders word-wrapped text to Pillow Images.

    Features:
    - Word-level wrapping with character fallback for long words
    - Line-level image caching for scroll performance
    - Configurable margins and line spacing
    """

    def __init__(
        self,
        width: int = 240,
        font_size: int = 18,
        color: tuple[int, int, int] = (255, 255, 255),
        margin: int = 8,
        line_spacing: int = 4,
    ) -> None:
        self.width = width
        self.font_size = font_size
        self.color = color
        self.margin = margin
        self.line_spacing = line_spacing
        self._font = get_font(font_size)
        self._cache: dict[tuple[str, int, tuple[int, int, int]], Image.Image] = {}

    @property
    def usable_width(self) -> int:
        """Width available for text after margins."""
        return self.width - 2 * self.margin

    @property
    def line_height(self) -> int:
        """Height of a single line including spacing."""
        bbox = self._font.getbbox("Ay")
        return int(bbox[3] - bbox[1]) + self.line_spacing

    def wrap_text(self, text: str) -> list[str]:
        """Word-wrap text to fit within usable_width.

        Uses word-level wrapping. Falls back to character-level
        splitting for words wider than the available width.
        """
        lines: list[str] = []
        for paragraph in text.split("\n"):
            if not paragraph.strip():
                lines.append("")
                continue
            words = paragraph.split()
            if not words:
                lines.append("")
                continue
            # Check if first word itself exceeds width
            bbox = self._font.getbbox(words[0])
            if (bbox[2] - bbox[0]) > self.usable_width:
                lines.extend(self._split_word(words[0]))
                current_line = ""
            else:
                current_line = words[0]
            for word in words[1:]:
                test = f"{current_line} {word}"
                bbox = self._font.getbbox(test)
                test_width = bbox[2] - bbox[0]
                if test_width <= self.usable_width:
                    current_line = test
                else:
                    lines.append(current_line)
                    # Character fallback for words wider than available width
                    bbox = self._font.getbbox(word)
                    word_width = bbox[2] - bbox[0]
                    if word_width > self.usable_width:
                        lines.extend(self._split_word(word))
                        current_line = ""
                    else:
                        current_line = word
            if current_line:
                lines.append(current_line)
        return lines if lines else [""]

    def _split_word(self, word: str) -> list[str]:
        """Split a single word that exceeds usable_width into fragments."""
        fragments: list[str] = []
        current = ""
        for ch in word:
            test = current + ch
            bbox = self._font.getbbox(test)
            if (bbox[2] - bbox[0]) > self.usable_width:
                if current:
                    fragments.append(current)
                current = ch
            else:
                current = test
        if current:
            fragments.append(current)
        return fragments

    def render_line(self, text: str) -> Image.Image:
        """Render a single line of text, using cache."""
        cache_key = (text, self.font_size, self.color)
        if cache_key in self._cache:
            return self._cache[cache_key]

        bbox = self._font.getbbox(text) if text else (0, 0, 0, 0)
        text_h = int(bbox[3] - bbox[1]) if text else self.line_height - self.line_spacing
        img = Image.new("RGB", (self.width, text_h), (0, 0, 0))
        if text:
            draw = ImageDraw.Draw(img)
            draw.text((self.margin, int(-bbox[1])), text, fill=self.color, font=self._font)

        self._cache[cache_key] = img
        return img

    def render_text(self, text: str) -> Image.Image:
        """Render word-wrapped text as a single tall image.

        Returns an image of width=self.width and height determined
        by the number of wrapped lines. Suitable for scrolling.
        """
        lines = self.wrap_text(text)
        total_height = max(len(lines) * self.line_height, 1)
        img = Image.new("RGB", (self.width, total_height), (0, 0, 0))

        y = 0
        for line in lines:
            line_img = self.render_line(line)
            img.paste(line_img, (0, y))
            y += self.line_height

        return img

    def measure_text(self, text: str) -> tuple[int, int]:
        """Measure the pixel dimensions of wrapped text.

        Returns:
            (width, height) in pixels.
        """
        lines = self.wrap_text(text)
        return self.width, len(lines) * self.line_height

    def clear_cache(self) -> None:
        """Clear the line image cache (call on state transitions)."""
        self._cache.clear()
