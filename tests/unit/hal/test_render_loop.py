"""Tests for RenderLoop — dirty flag, timing, scroll, state transitions."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from PIL import Image

from cortex.hal.display.render_loop import RenderLoop
from cortex.hal.display.renderer import LCD_HEIGHT, LCD_WIDTH, FrameRenderer
from cortex.hal.types import DisplayState


@pytest.fixture()
def renderer() -> FrameRenderer:
    return FrameRenderer()


@pytest.fixture()
def mock_driver() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def loop(renderer: FrameRenderer, mock_driver: MagicMock) -> RenderLoop:
    return RenderLoop(renderer=renderer, driver=mock_driver)


class TestRenderLoopInit:
    """Initial state."""

    def test_initial_state_idle(self, loop: RenderLoop) -> None:
        assert loop.state == DisplayState.IDLE

    def test_initial_text_empty(self, loop: RenderLoop) -> None:
        assert loop.text == ""

    def test_not_running_initially(self, loop: RenderLoop) -> None:
        assert not loop.is_running

    def test_no_last_frame(self, loop: RenderLoop) -> None:
        assert loop.last_frame is None


class TestStateChanges:
    """State and text updates mark dirty flag."""

    def test_set_state(self, loop: RenderLoop) -> None:
        loop.set_state(DisplayState.LISTENING)
        assert loop.state == DisplayState.LISTENING

    def test_set_state_resets_frame_num(self, loop: RenderLoop) -> None:
        loop._frame_num = 42
        loop.set_state(DisplayState.THINKING)
        assert loop.frame_num == 0

    def test_set_state_resets_scroll(self, loop: RenderLoop) -> None:
        loop._scroll_offset = 100
        loop.set_state(DisplayState.SPEAKING)
        assert loop.scroll_offset == 0

    def test_set_text(self, loop: RenderLoop) -> None:
        loop.set_text("Hello")
        assert loop.text == "Hello"

    def test_same_state_not_dirty(self, loop: RenderLoop) -> None:
        loop._dirty = False
        loop.set_state(DisplayState.IDLE)  # same state
        assert not loop._dirty

    def test_same_text_not_dirty(self, loop: RenderLoop) -> None:
        loop.set_text("Test")
        loop._dirty = False
        loop.set_text("Test")  # same text
        assert not loop._dirty

    def test_different_state_marks_dirty(self, loop: RenderLoop) -> None:
        loop._dirty = False
        loop.set_state(DisplayState.LISTENING)
        assert loop._dirty

    def test_different_text_marks_dirty(self, loop: RenderLoop) -> None:
        loop._dirty = False
        loop.set_text("New text")
        assert loop._dirty


class TestRenderLoopLifecycle:
    """Start/stop behavior."""

    async def test_start_sets_running(self, loop: RenderLoop) -> None:
        await loop.start()
        assert loop.is_running
        await loop.stop()

    async def test_stop_clears_running(self, loop: RenderLoop) -> None:
        await loop.start()
        await loop.stop()
        assert not loop.is_running

    async def test_double_start_safe(self, loop: RenderLoop) -> None:
        await loop.start()
        await loop.start()  # should not crash
        assert loop.is_running
        await loop.stop()

    async def test_stop_without_start_safe(self, loop: RenderLoop) -> None:
        await loop.stop()  # should not crash

    async def test_renders_frame_after_start(self, loop: RenderLoop) -> None:
        await loop.start()
        await asyncio.sleep(0.1)  # let at least one frame render
        await loop.stop()
        assert loop.last_frame is not None
        assert loop.last_frame.size == (LCD_WIDTH, LCD_HEIGHT)

    async def test_driver_called(
        self, loop: RenderLoop, mock_driver: MagicMock,
    ) -> None:
        await loop.start()
        await asyncio.sleep(0.1)
        await loop.stop()
        mock_driver.write_frame.assert_called()
        # Verify the data is correct size (RGB565)
        data = mock_driver.write_frame.call_args[0][0]
        assert len(data) == LCD_WIDTH * LCD_HEIGHT * 2


class TestRenderLoopNoDriver:
    """Works without hardware driver."""

    async def test_no_driver_renders(self, renderer: FrameRenderer) -> None:
        loop = RenderLoop(renderer=renderer, driver=None)
        await loop.start()
        await asyncio.sleep(0.1)
        await loop.stop()
        assert loop.last_frame is not None


class TestAnimatedStates:
    """Animated states render continuously."""

    async def test_listening_advances_frame(self, loop: RenderLoop) -> None:
        loop.set_state(DisplayState.LISTENING)
        await loop.start()
        await asyncio.sleep(0.15)
        await loop.stop()
        assert loop.frame_num > 1

    async def test_thinking_advances_frame(self, loop: RenderLoop) -> None:
        loop.set_state(DisplayState.THINKING)
        await loop.start()
        await asyncio.sleep(0.15)
        await loop.stop()
        assert loop.frame_num > 1

    async def test_speaking_auto_scrolls(self, loop: RenderLoop) -> None:
        loop.set_state(DisplayState.SPEAKING)
        loop.set_text("Line " * 50)
        await loop.start()
        await asyncio.sleep(0.15)
        await loop.stop()
        assert loop.scroll_offset > 0


class TestOnFrameCallback:
    """Callback fires after each render."""

    async def test_callback_fired(self, loop: RenderLoop) -> None:
        frames: list[Image.Image] = []
        loop.on_frame(lambda img: frames.append(img))
        await loop.start()
        await asyncio.sleep(0.1)
        await loop.stop()
        assert len(frames) > 0
        assert all(isinstance(f, Image.Image) for f in frames)
