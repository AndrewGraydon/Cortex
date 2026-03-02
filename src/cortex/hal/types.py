"""HAL data types — hardware-agnostic types for NPU, audio, display, button."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

# --- NPU Types ---


@dataclass(frozen=True)
class ModelHandle:
    """Opaque handle returned by NpuService.load_model."""

    model_id: str
    _internal: Any = field(default=None, repr=False, compare=False)


@dataclass
class InferenceInputs:
    """Generic inference inputs — model-specific interpretation."""

    data: NDArray[np.float32] | NDArray[np.int16] | bytes | str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class InferenceOutputs:
    """Generic inference outputs — model-specific interpretation."""

    data: NDArray[np.float32] | NDArray[np.int16] | bytes | str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NpuCapabilities:
    """Static NPU capabilities — set once at init."""

    total_memory_mb: int
    compute_tops: float
    supported_formats: list[str] = field(default_factory=lambda: ["axmodel"])


@dataclass
class NpuStatus:
    """Dynamic NPU status — polled periodically."""

    temperature_c: float
    memory_used_mb: int
    memory_total_mb: int
    models_loaded: list[str] = field(default_factory=list)


# --- Audio Types ---


class AudioFormat(enum.Enum):
    """Audio sample formats."""

    S16_LE = "S16_LE"
    FLOAT32 = "FLOAT32"


@dataclass
class AudioData:
    """Audio buffer with metadata."""

    samples: NDArray[np.int16] | NDArray[np.float32]
    sample_rate: int
    channels: int = 1
    format: AudioFormat = AudioFormat.S16_LE


# --- Display Types ---


class DisplayState(enum.Enum):
    """LCD display states matching voice pipeline phases."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ALERT = "alert"
    ERROR = "error"


@dataclass(frozen=True)
class LedColor:
    """RGB LED color (0-255 per channel)."""

    r: int
    g: int
    b: int

    @classmethod
    def idle(cls) -> LedColor:
        return cls(0, 0, 85)  # dim blue

    @classmethod
    def listening(cls) -> LedColor:
        return cls(0, 255, 0)  # green

    @classmethod
    def thinking(cls) -> LedColor:
        return cls(255, 170, 0)  # amber

    @classmethod
    def speaking(cls) -> LedColor:
        return cls(0, 100, 255)  # blue

    @classmethod
    def error(cls) -> LedColor:
        return cls(255, 0, 0)  # red

    @classmethod
    def off(cls) -> LedColor:
        return cls(0, 0, 0)


# --- Button Types ---


class ButtonGesture(enum.Enum):
    """Recognized button gestures (from gesture state machine)."""

    HOLD_START = "hold_start"
    HOLD_END = "hold_end"
    SINGLE_CLICK = "single_click"
    DOUBLE_CLICK = "double_click"
    LONG_PRESS = "long_press"
    TRIPLE_CLICK = "triple_click"


@dataclass(frozen=True)
class ButtonEvent:
    """Button gesture event with timestamp."""

    gesture: ButtonGesture
    timestamp: float  # time.monotonic()
    duration_ms: float = 0.0  # for hold/long_press
