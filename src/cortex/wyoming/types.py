"""Wyoming bridge types — audio format conversion and status tracking."""

from __future__ import annotations

import enum
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


class BridgeState(enum.Enum):
    """Wyoming bridge lifecycle state."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"


class NpuAvailability(enum.Enum):
    """NPU availability for Wyoming requests."""

    AVAILABLE = "available"
    BUSY = "busy"  # Voice pipeline active
    UNAVAILABLE = "unavailable"  # Model not loaded


@dataclass(frozen=True)
class AudioFormat:
    """Audio format specification."""

    rate: int = 16000
    width: int = 2  # bytes per sample (2 = int16)
    channels: int = 1


# Standard formats used by Wyoming ↔ Cortex bridge
WYOMING_STT_FORMAT = AudioFormat(rate=16000, width=2, channels=1)
WYOMING_TTS_FORMAT = AudioFormat(rate=22050, width=2, channels=1)
CORTEX_ASR_FORMAT = AudioFormat(rate=16000, width=2, channels=1)
CORTEX_TTS_FORMAT = AudioFormat(rate=24000, width=2, channels=1)


def pcm_int16_to_float32(audio: bytes, *, rate: int = 16000) -> NDArray[np.float32]:
    """Convert raw PCM int16 bytes to float32 numpy array.

    Args:
        audio: Raw PCM bytes (int16, little-endian).
        rate: Sample rate (for documentation; not used in conversion).

    Returns:
        Float32 numpy array normalized to [-1.0, 1.0].
    """
    _ = rate  # rate is for caller context only
    samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32)
    return samples / 32768.0


def float32_to_pcm_int16(audio: NDArray[np.float32]) -> bytes:
    """Convert float32 numpy array to raw PCM int16 bytes.

    Args:
        audio: Float32 numpy array (expected range [-1.0, 1.0]).

    Returns:
        Raw PCM bytes (int16, little-endian).
    """
    clipped = np.clip(audio, -1.0, 1.0)
    int16_audio = (clipped * 32767).astype(np.int16)
    return int16_audio.tobytes()


def resample_linear(
    audio: NDArray[np.float32],
    src_rate: int,
    dst_rate: int,
) -> NDArray[np.float32]:
    """Resample audio using linear interpolation.

    Simple and fast — suitable for voice audio where high-fidelity
    resampling isn't critical. Avoids scipy/librosa dependency.

    Args:
        audio: Input float32 samples.
        src_rate: Source sample rate (e.g. 24000).
        dst_rate: Destination sample rate (e.g. 22050).

    Returns:
        Resampled float32 array.
    """
    if src_rate == dst_rate:
        return audio

    if len(audio) == 0:
        return audio

    ratio = dst_rate / src_rate
    new_length = int(len(audio) * ratio)
    if new_length == 0:
        return np.array([], dtype=np.float32)

    indices = np.linspace(0, len(audio) - 1, new_length)
    return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)
