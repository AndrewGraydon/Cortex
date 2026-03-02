"""HAL Protocol interfaces — hardware-agnostic service contracts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol, runtime_checkable

from cortex.hal.types import (
    AudioData,
    ButtonEvent,
    DisplayState,
    InferenceInputs,
    InferenceOutputs,
    LedColor,
    ModelHandle,
    NpuCapabilities,
    NpuStatus,
)


@runtime_checkable
class NpuService(Protocol):
    """Hardware-agnostic NPU service interface.

    All model-specific logic (axmodel format, CMM memory management,
    context switching) lives inside the implementation (e.g. AxclNpuService).
    """

    async def load_model(self, model_id: str, model_path: Path) -> ModelHandle: ...

    async def unload_model(self, handle: ModelHandle) -> None: ...

    async def infer(self, handle: ModelHandle, inputs: InferenceInputs) -> InferenceOutputs: ...

    async def infer_stream(
        self, handle: ModelHandle, inputs: InferenceInputs
    ) -> AsyncIterator[InferenceOutputs]: ...

    async def get_status(self) -> NpuStatus: ...

    @property
    def capabilities(self) -> NpuCapabilities: ...


@runtime_checkable
class AudioService(Protocol):
    """Audio capture and playback service.

    Capture: 16kHz mono S16_LE from WM8960 codec.
    Playback: 24kHz S16_LE to WM8960, streaming with ~50ms buffers.
    """

    async def start_capture(self, sample_rate: int = 16000) -> None: ...

    async def stop_capture(self) -> AudioData: ...

    async def play(self, audio: AudioData) -> None: ...

    async def play_stream(self, chunks: AsyncIterator[AudioData]) -> None: ...

    async def stop_playback(self) -> None: ...

    @property
    def is_capturing(self) -> bool: ...

    @property
    def is_playing(self) -> bool: ...


@runtime_checkable
class DisplayService(Protocol):
    """LCD display and LED control service.

    ST7789 240x280 SPI0, Pillow rendering.
    RGB LED via PWM on pins 22/18/16 (active-low).
    """

    async def set_state(self, state: DisplayState, text: str = "") -> None: ...

    async def set_led(self, color: LedColor) -> None: ...

    async def show_text(self, text: str, scroll: bool = False) -> None: ...

    async def get_state(self) -> DisplayState: ...


@runtime_checkable
class ButtonService(Protocol):
    """Button gesture detection service.

    GPIO 11, active-HIGH, BOARD numbering.
    Gesture state machine with debounce.
    """

    async def wait_gesture(self) -> ButtonEvent: ...

    def subscribe(self) -> AsyncIterator[ButtonEvent]: ...
