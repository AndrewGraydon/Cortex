"""Tests for TextRenderer — word wrap, caching, font loading."""

from __future__ import annotations

import pytest
from PIL import Image

from cortex.hal.display.text import TextRenderer, get_font


class TestGetFont:
    """Font loading with caching."""

    def test_returns_freetype_font(self) -> None:
        from PIL.ImageFont import FreeTypeFont

        font = get_font(18)
        assert isinstance(font, FreeTypeFont)

    def test_cached_across_calls(self) -> None:
        f1 = get_font(24)
        f2 = get_font(24)
        assert f1 is f2

    def test_different_sizes_different_fonts(self) -> None:
        f1 = get_font(12)
        f2 = get_font(24)
        assert f1 is not f2


class TestWordWrap:
    """Word-level wrapping with character fallback."""

    @pytest.fixture()
    def renderer(self) -> TextRenderer:
        return TextRenderer(width=240, font_size=18, margin=8)

    def test_short_text_single_line(self, renderer: TextRenderer) -> None:
        lines = renderer.wrap_text("Hello")
        assert lines == ["Hello"]

    def test_empty_text(self, renderer: TextRenderer) -> None:
        lines = renderer.wrap_text("")
        assert lines == [""]

    def test_newlines_preserved(self, renderer: TextRenderer) -> None:
        lines = renderer.wrap_text("Line 1\nLine 2")
        assert "Line 1" in lines
        assert "Line 2" in lines

    def test_long_text_wraps(self, renderer: TextRenderer) -> None:
        long_text = (
            "This is a much longer sentence that should"
            " wrap to multiple lines on the display"
        )
        lines = renderer.wrap_text(long_text)
        assert len(lines) > 1
        # All words should be present across lines
        joined = " ".join(lines)
        for word in long_text.split():
            assert word in joined

    def test_very_long_word_split(self) -> None:
        """Words wider than usable_width are character-split."""
        renderer = TextRenderer(width=100, font_size=18, margin=8)
        # Usable width = 84px, this word is ~200+ chars
        long_word = "A" * 200
        lines = renderer.wrap_text(long_word)
        assert len(lines) > 1
        # All characters preserved
        assert "".join(lines) == long_word

    def test_blank_lines_preserved(self, renderer: TextRenderer) -> None:
        lines = renderer.wrap_text("Para 1\n\nPara 2")
        assert "" in lines

    def test_usable_width(self, renderer: TextRenderer) -> None:
        assert renderer.usable_width == 224  # 240 - 2*8


class TestTextRendering:
    """Rendering text to images."""

    @pytest.fixture()
    def renderer(self) -> TextRenderer:
        return TextRenderer(width=240, font_size=18)

    def test_render_line_returns_image(self, renderer: TextRenderer) -> None:
        img = renderer.render_line("Hello World")
        assert isinstance(img, Image.Image)
        assert img.width == 240

    def test_render_empty_line(self, renderer: TextRenderer) -> None:
        img = renderer.render_line("")
        assert isinstance(img, Image.Image)
        assert img.width == 240

    def test_render_text_returns_image(self, renderer: TextRenderer) -> None:
        img = renderer.render_text("Hello World")
        assert isinstance(img, Image.Image)
        assert img.width == 240
        assert img.height > 0

    def test_render_text_multiline_taller(self, renderer: TextRenderer) -> None:
        short = renderer.render_text("Hi")
        long_text = "This is a much longer text that should definitely wrap across several lines"
        tall = renderer.render_text(long_text)
        assert tall.height > short.height

    def test_render_text_white_on_black(self, renderer: TextRenderer) -> None:
        img = renderer.render_text("Test")
        # Background should be black (0,0,0)
        corner = img.getpixel((0, 0))
        assert corner == (0, 0, 0)

    def test_custom_color(self) -> None:
        renderer = TextRenderer(color=(0, 255, 0))
        img = renderer.render_text("Green")
        # Should have some green pixels
        pixels = list(img.get_flattened_data())
        has_green = any(p[1] > 200 and p[0] < 50 and p[2] < 50 for p in pixels)
        assert has_green

    def test_measure_text(self, renderer: TextRenderer) -> None:
        w, h = renderer.measure_text("Hello")
        assert w == 240
        assert h > 0

    def test_measure_multiline(self, renderer: TextRenderer) -> None:
        _, h1 = renderer.measure_text("Short")
        _, h2 = renderer.measure_text("Line 1\nLine 2\nLine 3")
        assert h2 > h1


class TestLineCache:
    """Line-level image caching."""

    @pytest.fixture()
    def renderer(self) -> TextRenderer:
        return TextRenderer(width=240, font_size=18)

    def test_cache_hit(self, renderer: TextRenderer) -> None:
        img1 = renderer.render_line("Cached line")
        img2 = renderer.render_line("Cached line")
        assert img1 is img2

    def test_cache_miss_different_text(self, renderer: TextRenderer) -> None:
        img1 = renderer.render_line("Line A")
        img2 = renderer.render_line("Line B")
        assert img1 is not img2

    def test_cache_clear(self, renderer: TextRenderer) -> None:
        img1 = renderer.render_line("Before clear")
        renderer.clear_cache()
        img2 = renderer.render_line("Before clear")
        assert img1 is not img2

    def test_cache_key_includes_color(self) -> None:
        r1 = TextRenderer(color=(255, 0, 0))
        r2 = TextRenderer(color=(0, 255, 0))
        # Different color renderers have independent caches
        img1 = r1.render_line("Test")
        img2 = r2.render_line("Test")
        assert img1 is not img2


class TestLineHeight:
    """Line height calculation."""

    def test_line_height_positive(self) -> None:
        renderer = TextRenderer(font_size=18)
        assert renderer.line_height > 0

    def test_larger_font_taller_lines(self) -> None:
        small = TextRenderer(font_size=12)
        large = TextRenderer(font_size=24)
        assert large.line_height > small.line_height
