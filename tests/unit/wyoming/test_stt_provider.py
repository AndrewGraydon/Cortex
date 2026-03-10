"""Tests for Wyoming STT provider."""

from __future__ import annotations

import numpy as np
import pytest

from cortex.wyoming.stt_provider import (
    MockAsrBackend,
    SttEventHandler,
    SttProvider,
)
from cortex.wyoming.types import NpuAvailability


@pytest.fixture
def mock_backend() -> MockAsrBackend:
    return MockAsrBackend(transcript="hello world")


@pytest.fixture
def provider(mock_backend: MockAsrBackend) -> SttProvider:
    return SttProvider(backend=mock_backend, model_name="sensevoice")


@pytest.fixture
def handler(provider: SttProvider) -> SttEventHandler:
    return SttEventHandler(provider)


class TestSttProviderInfo:
    """Service info for Describe events."""

    def test_info_has_asr_program(self, provider: SttProvider) -> None:
        info = provider.get_info()
        assert "asr" in info
        assert len(info["asr"]) == 1

    def test_info_model_name(self, provider: SttProvider) -> None:
        info = provider.get_info()
        assert info["asr"][0]["name"] == "sensevoice"

    def test_info_installed(self, provider: SttProvider) -> None:
        info = provider.get_info()
        assert info["asr"][0]["installed"] is True

    def test_info_languages(self, provider: SttProvider) -> None:
        info = provider.get_info()
        models = info["asr"][0]["models"]
        assert len(models) == 1
        assert "en" in models[0]["languages"]

    def test_custom_languages(self, mock_backend: MockAsrBackend) -> None:
        p = SttProvider(backend=mock_backend, languages=["en", "zh", "ja"])
        info = p.get_info()
        langs = info["asr"][0]["models"][0]["languages"]
        assert langs == ["en", "zh", "ja"]


class TestSttProviderTranscription:
    """Audio buffering and transcription."""

    async def test_basic_transcription(self, provider: SttProvider) -> None:
        """Accumulate audio → finish → get transcript."""
        provider.begin_session()
        # Simulate 1 second of 16kHz mono int16 audio
        audio = np.zeros(16000, dtype=np.int16).tobytes()
        provider.add_audio(audio)
        assert provider.buffered_bytes == 32000  # 16000 samples × 2 bytes

        result = await provider.finish()
        assert result == "hello world"

    async def test_empty_buffer_returns_empty(self, provider: SttProvider) -> None:
        provider.begin_session()
        result = await provider.finish()
        assert result == ""

    async def test_buffered_bytes_tracking(self, provider: SttProvider) -> None:
        provider.begin_session()
        assert provider.buffered_bytes == 0
        provider.add_audio(b"\x00" * 100)
        assert provider.buffered_bytes == 100
        provider.add_audio(b"\x00" * 200)
        assert provider.buffered_bytes == 300

    async def test_buffer_cleared_after_finish(self, provider: SttProvider) -> None:
        provider.begin_session()
        provider.add_audio(b"\x00" * 100)
        await provider.finish()
        assert provider.buffered_bytes == 0

    async def test_multiple_sessions(self, provider: SttProvider) -> None:
        """Each session starts fresh."""
        provider.begin_session()
        provider.add_audio(np.zeros(1000, dtype=np.int16).tobytes())
        result1 = await provider.finish()
        assert result1 == "hello world"

        provider.begin_session()
        provider.add_audio(np.zeros(500, dtype=np.int16).tobytes())
        result2 = await provider.finish()
        assert result2 == "hello world"

    async def test_backend_receives_float32(
        self, provider: SttProvider, mock_backend: MockAsrBackend
    ) -> None:
        """Backend receives float32 audio converted from int16 PCM."""
        provider.begin_session()
        audio = np.zeros(1600, dtype=np.int16).tobytes()
        provider.add_audio(audio)
        await provider.finish()
        assert mock_backend.last_audio_length == 1600

    async def test_whitespace_stripped(self, mock_backend: MockAsrBackend) -> None:
        mock_backend._transcript = "  hello world  "
        p = SttProvider(backend=mock_backend)
        p.begin_session()
        p.add_audio(np.zeros(100, dtype=np.int16).tobytes())
        result = await p.finish()
        assert result == "hello world"


class TestSttProviderNpuAvailability:
    """NPU availability gating."""

    async def test_busy_returns_empty(self, mock_backend: MockAsrBackend) -> None:
        p = SttProvider(
            backend=mock_backend,
            availability_fn=lambda: NpuAvailability.BUSY,
        )
        p.begin_session()
        p.add_audio(np.zeros(1000, dtype=np.int16).tobytes())
        result = await p.finish()
        assert result == ""

    async def test_unavailable_returns_empty(self, mock_backend: MockAsrBackend) -> None:
        p = SttProvider(
            backend=mock_backend,
            availability_fn=lambda: NpuAvailability.UNAVAILABLE,
        )
        p.begin_session()
        p.add_audio(np.zeros(1000, dtype=np.int16).tobytes())
        result = await p.finish()
        assert result == ""

    async def test_available_processes(self, mock_backend: MockAsrBackend) -> None:
        p = SttProvider(
            backend=mock_backend,
            availability_fn=lambda: NpuAvailability.AVAILABLE,
        )
        p.begin_session()
        p.add_audio(np.zeros(1000, dtype=np.int16).tobytes())
        result = await p.finish()
        assert result == "hello world"


class TestSttProviderErrorHandling:
    """Error handling during transcription."""

    async def test_backend_exception_returns_empty(self) -> None:
        class FailingBackend:
            async def transcribe(self, audio: np.ndarray) -> str:
                msg = "NPU error"
                raise RuntimeError(msg)

        p = SttProvider(backend=FailingBackend())  # type: ignore[arg-type]
        p.begin_session()
        p.add_audio(np.zeros(100, dtype=np.int16).tobytes())
        result = await p.finish()
        assert result == ""

    async def test_double_finish_raises(self, provider: SttProvider) -> None:
        """Cannot call finish() while already processing."""
        provider.begin_session()
        provider.add_audio(np.zeros(100, dtype=np.int16).tobytes())
        # First finish works
        await provider.finish()
        # Second finish on empty buffer returns empty (no error)
        result = await provider.finish()
        assert result == ""


class TestSttEventHandler:
    """Event handler protocol tests."""

    async def test_handle_describe(self, handler: SttEventHandler) -> None:
        info = await handler.handle_describe()
        assert "asr" in info

    async def test_handle_transcribe_then_audio(self, handler: SttEventHandler) -> None:
        await handler.handle_transcribe(language="en")
        await handler.handle_audio_chunk(np.zeros(1000, dtype=np.int16).tobytes())
        result = await handler.handle_audio_stop()
        assert result == "hello world"

    async def test_handle_empty_audio(self, handler: SttEventHandler) -> None:
        await handler.handle_transcribe()
        result = await handler.handle_audio_stop()
        assert result == ""
