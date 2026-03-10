"""Frame renderer — generates Pillow images for each DisplayState.

Pure software rendering, no hardware dependency. Each display state
has a dedicated render method producing a 240×280 RGB image.
"""

from __future__ import annotations

import math
from datetime import datetime

from PIL import Image, ImageDraw

from cortex.hal.display.text import TextRenderer
from cortex.hal.types import DisplayState

# LCD dimensions
LCD_WIDTH = 240
LCD_HEIGHT = 280

# Color palette — matches LedColor factory methods in types.py
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (128, 128, 128)
DIM_BLUE = (0, 0, 85)
GREEN = (0, 255, 0)
AMBER = (255, 170, 0)
BLUE = (0, 100, 255)
RED = (255, 0, 0)

# Border width for state indicators
BORDER_W = 3


class FrameRenderer:
    """Renders display frames for each DisplayState.

    All methods return a 240×280 RGB Pillow Image.
    """

    def __init__(self) -> None:
        self._title_text = TextRenderer(
            width=LCD_WIDTH, font_size=24, color=WHITE, margin=8,
        )
        self._body_text = TextRenderer(
            width=LCD_WIDTH, font_size=18, color=WHITE, margin=10,
        )
        self._small_text = TextRenderer(
            width=LCD_WIDTH, font_size=14, color=GRAY, margin=8,
        )

    def render(
        self,
        state: DisplayState,
        text: str = "",
        frame_num: int = 0,
        scroll_offset: int = 0,
    ) -> Image.Image:
        """Render a frame for the given state.

        Args:
            state: Current display state.
            text: Text content (response text, error message, etc.).
            frame_num: Animation frame counter (for pulsing effects).
            scroll_offset: Vertical scroll offset in pixels (for SPEAKING).

        Returns:
            240×280 RGB Image.
        """
        dispatch = {
            DisplayState.IDLE: self._render_idle,
            DisplayState.LISTENING: self._render_listening,
            DisplayState.THINKING: self._render_thinking,
            DisplayState.SPEAKING: self._render_speaking,
            DisplayState.ALERT: self._render_alert,
            DisplayState.ERROR: self._render_error,
        }
        method = dispatch.get(state, self._render_idle)
        return method(text=text, frame_num=frame_num, scroll_offset=scroll_offset)

    def clear_cache(self) -> None:
        """Clear text renderer caches (call on state transitions)."""
        self._title_text.clear_cache()
        self._body_text.clear_cache()
        self._small_text.clear_cache()

    def _render_idle(
        self, text: str = "", frame_num: int = 0, scroll_offset: int = 0,
    ) -> Image.Image:
        """IDLE: Black bg, 'Cortex' centered, clock below, dim blue accent."""
        img = Image.new("RGB", (LCD_WIDTH, LCD_HEIGHT), BLACK)
        draw = ImageDraw.Draw(img)

        # "Cortex" centered
        title_font = self._title_text._font
        title = "Cortex"
        bbox = title_font.getbbox(title)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (LCD_WIDTH - tw) // 2
        ty = (LCD_HEIGHT // 2) - th - 10
        draw.text((tx, ty), title, fill=WHITE, font=title_font)

        # Clock below title
        clock = datetime.now().strftime("%H:%M")
        clock_font = self._small_text._font
        bbox = clock_font.getbbox(clock)
        cw = bbox[2] - bbox[0]
        cx = (LCD_WIDTH - cw) // 2
        cy = ty + th + 20
        draw.text((cx, cy), clock, fill=GRAY, font=clock_font)

        # Dim blue accent line
        line_y = LCD_HEIGHT - 30
        draw.line([(40, line_y), (LCD_WIDTH - 40, line_y)], fill=DIM_BLUE, width=2)

        return img

    def _render_listening(
        self, text: str = "", frame_num: int = 0, scroll_offset: int = 0,
    ) -> Image.Image:
        """LISTENING: Green border, 'Listening...' text, pulsing green dot."""
        img = Image.new("RGB", (LCD_WIDTH, LCD_HEIGHT), BLACK)
        draw = ImageDraw.Draw(img)

        # Green border
        _draw_border(draw, GREEN, BORDER_W)

        # "Listening..." centered
        title_font = self._title_text._font
        label = "Listening..."
        bbox = title_font.getbbox(label)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (LCD_WIDTH - tw) // 2
        ty = LCD_HEIGHT // 2 - th
        draw.text((tx, ty), label, fill=GREEN, font=title_font)

        # Pulsing green dot (sine wave brightness)
        pulse = (math.sin(frame_num * 0.2) + 1) / 2  # 0..1
        brightness = int(80 + 175 * pulse)
        dot_color = (0, brightness, 0)
        cx, cy = LCD_WIDTH // 2, ty + th + 30
        r = 6
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=dot_color)

        return img

    def _render_thinking(
        self, text: str = "", frame_num: int = 0, scroll_offset: int = 0,
    ) -> Image.Image:
        """THINKING: Amber border, 'Thinking' with cycling dots."""
        img = Image.new("RGB", (LCD_WIDTH, LCD_HEIGHT), BLACK)
        draw = ImageDraw.Draw(img)

        # Amber border
        _draw_border(draw, AMBER, BORDER_W)

        # "Thinking" with 1-3 cycling dots
        dot_count = (frame_num // 10 % 3) + 1
        label = "Thinking" + "." * dot_count
        title_font = self._title_text._font
        bbox = title_font.getbbox(label)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (LCD_WIDTH - tw) // 2
        ty = LCD_HEIGHT // 2 - th
        draw.text((tx, ty), label, fill=AMBER, font=title_font)

        return img

    def _render_speaking(
        self, text: str = "", frame_num: int = 0, scroll_offset: int = 0,
    ) -> Image.Image:
        """SPEAKING: Blue accent header, word-wrapped response, scrollable."""
        img = Image.new("RGB", (LCD_WIDTH, LCD_HEIGHT), BLACK)
        draw = ImageDraw.Draw(img)

        # Blue accent header bar
        header_h = 32
        draw.rectangle([0, 0, LCD_WIDTH, header_h], fill=BLUE)
        header_font = self._small_text._font
        draw.text((10, 8), "Response", fill=WHITE, font=header_font)

        # Body text — render full text then crop with scroll offset
        if text:
            text_img = self._body_text.render_text(text)
            body_area_h = LCD_HEIGHT - header_h
            # Clamp scroll offset
            max_scroll = max(0, text_img.height - body_area_h)
            offset = min(scroll_offset, max_scroll)
            # Crop the visible region
            crop_box = (0, offset, LCD_WIDTH, min(offset + body_area_h, text_img.height))
            visible = text_img.crop(crop_box)
            img.paste(visible, (0, header_h))

        return img

    def _render_alert(
        self, text: str = "", frame_num: int = 0, scroll_offset: int = 0,
    ) -> Image.Image:
        """ALERT: Red border, action description, approve/deny footer."""
        img = Image.new("RGB", (LCD_WIDTH, LCD_HEIGHT), BLACK)
        draw = ImageDraw.Draw(img)

        # Red border
        _draw_border(draw, RED, BORDER_W)

        # Alert text centered
        if text:
            body_font = self._body_text._font
            lines = self._body_text.wrap_text(text)
            line_h = self._body_text.line_height
            total_h = len(lines) * line_h
            start_y = (LCD_HEIGHT - total_h) // 2 - 20
            for i, line in enumerate(lines):
                bbox = body_font.getbbox(line)
                lw = bbox[2] - bbox[0]
                lx = (LCD_WIDTH - lw) // 2
                draw.text((lx, start_y + i * line_h), line, fill=WHITE, font=body_font)

        # Footer: approve/deny instructions
        footer_font = self._small_text._font
        footer = "Press = Approve / Hold = Deny"
        bbox = footer_font.getbbox(footer)
        fw = bbox[2] - bbox[0]
        fx = (LCD_WIDTH - fw) // 2
        draw.text((fx, LCD_HEIGHT - 30), footer, fill=GRAY, font=footer_font)

        return img

    def _render_error(
        self, text: str = "", frame_num: int = 0, scroll_offset: int = 0,
    ) -> Image.Image:
        """ERROR: Red border, error message centered."""
        img = Image.new("RGB", (LCD_WIDTH, LCD_HEIGHT), BLACK)
        draw = ImageDraw.Draw(img)

        # Red border
        _draw_border(draw, RED, BORDER_W)

        # Error message centered
        msg = text or "Error"
        body_font = self._body_text._font
        lines = self._body_text.wrap_text(msg)
        line_h = self._body_text.line_height
        total_h = len(lines) * line_h
        start_y = (LCD_HEIGHT - total_h) // 2
        for i, line in enumerate(lines):
            bbox = body_font.getbbox(line)
            lw = bbox[2] - bbox[0]
            lx = (LCD_WIDTH - lw) // 2
            draw.text((lx, start_y + i * line_h), line, fill=RED, font=body_font)

        return img


def _draw_border(
    draw: ImageDraw.ImageDraw,
    color: tuple[int, int, int],
    width: int,
) -> None:
    """Draw a rectangular border inside the frame."""
    for i in range(width):
        draw.rectangle(
            [i, i, LCD_WIDTH - 1 - i, LCD_HEIGHT - 1 - i],
            outline=color,
        )
