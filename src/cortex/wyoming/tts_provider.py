"""Wyoming TTS provider — wraps Kokoro TTS for Home Assistant.

Implements the Wyoming protocol flow:
  Client → Describe → Info (capabilities)
  Client → Synthesize (text + voice)
  Server → AudioStart → AudioChunk* → AudioStop
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
import structlog
from numpy.typing import NDArray

from cortex.wyoming.types import (
    CORTEX_TTS_FORMAT,
    WYOMING_TTS_FORMAT,
    NpuAvailability,
    float32_to_pcm_int16,
    resample_linear,
)

logger = structlog.get_logger()


@dataclass(frozen=True)
class TtsResult:
    """Result from TTS synthesis."""

    audio_bytes: bytes  # PCM int16 at Wyoming TTS rate (22050 Hz)
    rate: int = WYOMING_TTS_FORMAT.rate
    width: int = WYOMING_TTS_FORMAT.width
    channels: int = WYOMING_TTS_FORMAT.channels


class TtsBackend(Protocol):
    """Protocol for TTS inference backends."""

    async def synthesize(self, text: str, voice: str = "af_heart") -> NDArray[np.float32]:
        """Synthesize text to float32 audio at native rate (e.g. 24kHz)."""
        ...

    @property
    def sample_rate(self) -> int:
        """Native output sample rate."""
        ...


class MockTtsBackend:
    """Mock TTS backend for testing."""

    def __init__(self, duration_ms: int = 500) -> None:
        self._duration_ms = duration_ms
        self.last_text: str = ""
        self.last_voice: str = ""

    async def synthesize(self, text: str, voice: str = "af_heart") -> NDArray[np.float32]:
        self.last_text = text
        self.last_voice = voice
        num_samples = int(self.sample_rate * self._duration_ms / 1000)
        return np.zeros(num_samples, dtype=np.float32)

    @property
    def sample_rate(self) -> int:
        return CORTEX_TTS_FORMAT.rate  # 24000


@dataclass
class VoiceInfo:
    """Wyoming-compatible voice description."""

    name: str = "af_heart"
    language: str = "en"
    description: str = "Kokoro default voice"


class TtsProvider:
    """Wyoming TTS provider wrapping Cortex Kokoro TTS.

    Handles the Wyoming TTS protocol:
    1. Describe → returns TTS capability info
    2. Synthesize → runs TTS inference, returns audio chunks

    Output audio is resampled from Kokoro's native 24kHz to
    Wyoming's standard 22050Hz and converted to PCM int16.
    """

    def __init__(
        self,
        backend: TtsBackend,
        availability_fn: Any | None = None,
        model_name: str = "kokoro",
        voices: list[VoiceInfo] | None = None,
        chunk_samples: int = 4096,
    ) -> None:
        self._backend = backend
        self._availability_fn = availability_fn or (lambda: NpuAvailability.AVAILABLE)
        self._model_name = model_name
        self._voices = voices or [VoiceInfo()]
        self._chunk_samples = chunk_samples
        self._processing = False

    def get_info(self) -> dict[str, Any]:
        """Return Wyoming-compatible TTS service info."""
        return {
            "tts": [
                {
                    "name": self._model_name,
                    "description": f"Cortex {self._model_name} TTS (NPU-accelerated)",
                    "version": "1.0.0",
                    "attribution": {"name": "Cortex", "url": ""},
                    "installed": True,
                    "voices": [
                        {
                            "name": v.name,
                            "description": v.description,
                            "version": "1.0.0",
                            "attribution": {"name": "Kokoro", "url": ""},
                            "installed": True,
                            "languages": [v.language],
                        }
                        for v in self._voices
                    ],
                }
            ]
        }

    async def synthesize(self, text: str, voice: str = "af_heart") -> TtsResult:
        """Synthesize text to PCM audio.

        Args:
            text: Text to synthesize.
            voice: Voice name (default: af_heart).

        Returns:
            TtsResult with PCM int16 audio at 22050Hz.
        """
        availability = self._availability_fn()
        if availability == NpuAvailability.BUSY:
            logger.warning("NPU busy — rejecting TTS request")
            return TtsResult(audio_bytes=b"")
        if availability == NpuAvailability.UNAVAILABLE:
            logger.warning("NPU unavailable — rejecting TTS request")
            return TtsResult(audio_bytes=b"")

        if not text.strip():
            return TtsResult(audio_bytes=b"")

        self._processing = True
        try:
            audio_float = await self._backend.synthesize(text, voice=voice)
            # Resample from native rate (24kHz) to Wyoming rate (22050Hz)
            resampled = resample_linear(
                audio_float,
                src_rate=self._backend.sample_rate,
                dst_rate=WYOMING_TTS_FORMAT.rate,
            )
            pcm_bytes = float32_to_pcm_int16(resampled)
            return TtsResult(audio_bytes=pcm_bytes)
        except Exception:
            logger.exception("TTS synthesis failed")
            return TtsResult(audio_bytes=b"")
        finally:
            self._processing = False

    def chunk_audio(self, audio_bytes: bytes) -> list[bytes]:
        """Split audio bytes into chunks for streaming.

        Args:
            audio_bytes: Full PCM int16 audio.

        Returns:
            List of audio byte chunks.
        """
        if not audio_bytes:
            return []

        bytes_per_chunk = self._chunk_samples * WYOMING_TTS_FORMAT.width
        chunks: list[bytes] = []
        for i in range(0, len(audio_bytes), bytes_per_chunk):
            chunks.append(audio_bytes[i : i + bytes_per_chunk])
        return chunks

    @property
    def is_processing(self) -> bool:
        return self._processing


class TtsEventHandler:
    """Wyoming event handler for TTS requests.

    Pure-Python handler (no wyoming import) — the WyomingBridge
    adapts this to actual Wyoming events.
    """

    def __init__(self, provider: TtsProvider) -> None:
        self._provider = provider

    async def handle_describe(self) -> dict[str, Any]:
        """Handle Describe event → return Info dict."""
        return self._provider.get_info()

    async def handle_synthesize(
        self, text: str, voice: str = "af_heart"
    ) -> list[bytes]:
        """Handle Synthesize event → return list of audio chunks.

        Returns:
            List of PCM int16 byte chunks at 22050Hz.
            Empty list if synthesis fails.
        """
        result = await self._provider.synthesize(text, voice=voice)
        if not result.audio_bytes:
            return []
        return self._provider.chunk_audio(result.audio_bytes)
