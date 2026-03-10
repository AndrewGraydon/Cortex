"""Wyoming STT provider — wraps SenseVoice ASR for Home Assistant.

Implements the Wyoming protocol flow:
  Client → Describe → Info (capabilities)
  Client → Transcribe → AudioStart → AudioChunk* → AudioStop
  Server → Transcript (text result)
"""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np
import structlog

from cortex.wyoming.types import (
    NpuAvailability,
    pcm_int16_to_float32,
)

logger = structlog.get_logger()


class AsrBackend(Protocol):
    """Protocol for ASR inference backends."""

    async def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe float32 16kHz audio to text."""
        ...


class MockAsrBackend:
    """Mock ASR backend for testing."""

    def __init__(self, transcript: str = "hello world") -> None:
        self._transcript = transcript
        self.last_audio_length: int = 0

    async def transcribe(self, audio: np.ndarray) -> str:
        self.last_audio_length = len(audio)
        return self._transcript


class SttProvider:
    """Wyoming STT provider wrapping Cortex ASR.

    Handles the Wyoming event protocol for speech-to-text:
    1. Describe → returns ASR capability info
    2. Transcribe → sets language
    3. AudioChunk* → accumulates PCM audio
    4. AudioStop → runs ASR inference, returns transcript

    The provider checks NPU availability before processing.
    If the voice pipeline is active, returns a busy error.
    """

    def __init__(
        self,
        backend: AsrBackend,
        availability_fn: Any | None = None,
        model_name: str = "sensevoice",
        languages: list[str] | None = None,
    ) -> None:
        self._backend = backend
        self._availability_fn = availability_fn or (lambda: NpuAvailability.AVAILABLE)
        self._model_name = model_name
        self._languages = languages or ["en"]

        # Per-session state
        self._audio_buffer: bytearray = bytearray()
        self._language: str = "en"
        self._processing = False

    def get_info(self) -> dict[str, Any]:
        """Return Wyoming-compatible ASR service info.

        Used to respond to Describe events.
        """
        return {
            "asr": [
                {
                    "name": self._model_name,
                    "description": f"Cortex {self._model_name} ASR (NPU-accelerated)",
                    "version": "1.0.0",
                    "attribution": {"name": "Cortex", "url": ""},
                    "installed": True,
                    "models": [
                        {
                            "name": self._model_name,
                            "description": f"{self._model_name} on AX8850 NPU",
                            "version": "1.0.0",
                            "attribution": {"name": "FunASR", "url": ""},
                            "installed": True,
                            "languages": self._languages,
                        }
                    ],
                }
            ]
        }

    def begin_session(self, language: str = "en") -> None:
        """Start a new transcription session."""
        self._audio_buffer = bytearray()
        self._language = language
        self._processing = False

    def add_audio(self, audio_bytes: bytes) -> None:
        """Accumulate raw PCM int16 audio data."""
        self._audio_buffer.extend(audio_bytes)

    async def finish(self) -> str:
        """Run ASR inference on accumulated audio.

        Returns:
            Transcribed text, or error string if NPU unavailable.

        Raises:
            RuntimeError: If called while already processing.
        """
        if self._processing:
            msg = "STT already processing"
            raise RuntimeError(msg)

        availability = self._availability_fn()
        if availability == NpuAvailability.BUSY:
            logger.warning("NPU busy — rejecting STT request")
            return ""
        if availability == NpuAvailability.UNAVAILABLE:
            logger.warning("NPU unavailable — rejecting STT request")
            return ""

        if not self._audio_buffer:
            return ""

        self._processing = True
        try:
            audio_float = pcm_int16_to_float32(bytes(self._audio_buffer))
            transcript = await self._backend.transcribe(audio_float)
            return transcript.strip()
        except Exception:
            logger.exception("STT inference failed")
            return ""
        finally:
            self._processing = False
            self._audio_buffer = bytearray()

    @property
    def is_processing(self) -> bool:
        return self._processing

    @property
    def buffered_bytes(self) -> int:
        return len(self._audio_buffer)


class SttEventHandler:
    """Wyoming event handler for STT requests.

    Wraps SttProvider to handle the Wyoming event protocol.
    This is a pure-Python handler that doesn't import wyoming directly,
    making it testable without the wyoming dependency.

    The WyomingBridge (server.py) adapts this to actual Wyoming events.
    """

    def __init__(self, provider: SttProvider) -> None:
        self._provider = provider

    async def handle_describe(self) -> dict[str, Any]:
        """Handle Describe event → return Info dict."""
        return self._provider.get_info()

    async def handle_transcribe(self, language: str = "en") -> None:
        """Handle Transcribe event → prepare for audio."""
        self._provider.begin_session(language=language)

    async def handle_audio_chunk(self, audio: bytes) -> None:
        """Handle AudioChunk event → buffer audio."""
        self._provider.add_audio(audio)

    async def handle_audio_stop(self) -> str:
        """Handle AudioStop event → run inference, return transcript text."""
        return await self._provider.finish()
