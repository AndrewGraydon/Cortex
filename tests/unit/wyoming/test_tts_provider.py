"""Tests for Wyoming TTS provider."""

from __future__ import annotations

import numpy as np
import pytest

from cortex.wyoming.tts_provider import (
    MockTtsBackend,
    TtsEventHandler,
    TtsProvider,
    TtsResult,
    VoiceInfo,
)
from cortex.wyoming.types import WYOMING_TTS_FORMAT, NpuAvailability


@pytest.fixture
def mock_backend() -> MockTtsBackend:
    return MockTtsBackend(duration_ms=500)


@pytest.fixture
def provider(mock_backend: MockTtsBackend) -> TtsProvider:
    return TtsProvider(backend=mock_backend, model_name="kokoro")


@pytest.fixture
def handler(provider: TtsProvider) -> TtsEventHandler:
    return TtsEventHandler(provider)


class TestTtsProviderInfo:
    """Service info for Describe events."""

    def test_info_has_tts_program(self, provider: TtsProvider) -> None:
        info = provider.get_info()
        assert "tts" in info
        assert len(info["tts"]) == 1

    def test_info_model_name(self, provider: TtsProvider) -> None:
        info = provider.get_info()
        assert info["tts"][0]["name"] == "kokoro"

    def test_info_installed(self, provider: TtsProvider) -> None:
        info = provider.get_info()
        assert info["tts"][0]["installed"] is True

    def test_info_default_voice(self, provider: TtsProvider) -> None:
        info = provider.get_info()
        voices = info["tts"][0]["voices"]
        assert len(voices) == 1
        assert voices[0]["name"] == "af_heart"
        assert "en" in voices[0]["languages"]

    def test_custom_voices(self, mock_backend: MockTtsBackend) -> None:
        voices = [
            VoiceInfo(name="af_heart", language="en", description="Default"),
            VoiceInfo(name="bf_emma", language="en", description="Emma"),
        ]
        p = TtsProvider(backend=mock_backend, voices=voices)
        info = p.get_info()
        assert len(info["tts"][0]["voices"]) == 2
        assert info["tts"][0]["voices"][1]["name"] == "bf_emma"


class TestTtsProviderSynthesis:
    """TTS synthesis and audio output."""

    async def test_basic_synthesis(self, provider: TtsProvider) -> None:
        result = await provider.synthesize("Hello world")
        assert isinstance(result, TtsResult)
        assert len(result.audio_bytes) > 0

    async def test_output_format(self, provider: TtsProvider) -> None:
        """Output should be at Wyoming TTS rate (22050Hz)."""
        result = await provider.synthesize("Hello world")
        assert result.rate == WYOMING_TTS_FORMAT.rate
        assert result.width == WYOMING_TTS_FORMAT.width
        assert result.channels == WYOMING_TTS_FORMAT.channels

    async def test_resampling_24k_to_22050(
        self, provider: TtsProvider, mock_backend: MockTtsBackend
    ) -> None:
        """Backend outputs 24kHz; provider resamples to 22050Hz."""
        result = await provider.synthesize("Hello")
        # 500ms at 24kHz = 12000 samples → resampled to 22050Hz ≈ 11025 samples
        expected_samples = int(12000 * (22050 / 24000))
        actual_samples = len(result.audio_bytes) // 2  # 2 bytes per int16 sample
        assert abs(actual_samples - expected_samples) <= 2

    async def test_empty_text_returns_empty(self, provider: TtsProvider) -> None:
        result = await provider.synthesize("")
        assert result.audio_bytes == b""

    async def test_whitespace_only_returns_empty(self, provider: TtsProvider) -> None:
        result = await provider.synthesize("   ")
        assert result.audio_bytes == b""

    async def test_voice_passed_to_backend(
        self, provider: TtsProvider, mock_backend: MockTtsBackend
    ) -> None:
        await provider.synthesize("Hello", voice="bf_emma")
        assert mock_backend.last_voice == "bf_emma"

    async def test_text_passed_to_backend(
        self, provider: TtsProvider, mock_backend: MockTtsBackend
    ) -> None:
        await provider.synthesize("Test sentence")
        assert mock_backend.last_text == "Test sentence"


class TestTtsProviderNpuAvailability:
    """NPU availability gating."""

    async def test_busy_returns_empty(self, mock_backend: MockTtsBackend) -> None:
        p = TtsProvider(
            backend=mock_backend,
            availability_fn=lambda: NpuAvailability.BUSY,
        )
        result = await p.synthesize("Hello")
        assert result.audio_bytes == b""

    async def test_unavailable_returns_empty(self, mock_backend: MockTtsBackend) -> None:
        p = TtsProvider(
            backend=mock_backend,
            availability_fn=lambda: NpuAvailability.UNAVAILABLE,
        )
        result = await p.synthesize("Hello")
        assert result.audio_bytes == b""

    async def test_available_processes(self, mock_backend: MockTtsBackend) -> None:
        p = TtsProvider(
            backend=mock_backend,
            availability_fn=lambda: NpuAvailability.AVAILABLE,
        )
        result = await p.synthesize("Hello")
        assert len(result.audio_bytes) > 0


class TestTtsProviderErrorHandling:
    """Error handling during synthesis."""

    async def test_backend_exception_returns_empty(self) -> None:
        class FailingBackend:
            async def synthesize(self, text: str, voice: str = "af_heart") -> np.ndarray:
                msg = "NPU error"
                raise RuntimeError(msg)

            @property
            def sample_rate(self) -> int:
                return 24000

        p = TtsProvider(backend=FailingBackend())  # type: ignore[arg-type]
        result = await p.synthesize("Hello")
        assert result.audio_bytes == b""


class TestTtsProviderChunking:
    """Audio chunking for streaming delivery."""

    def test_chunk_audio(self, provider: TtsProvider) -> None:
        audio_bytes = b"\x00" * 20000
        chunks = provider.chunk_audio(audio_bytes)
        assert len(chunks) > 1
        # All chunks except possibly last should be chunk_samples × width bytes
        expected_size = 4096 * 2  # default chunk_samples × 2 bytes
        for chunk in chunks[:-1]:
            assert len(chunk) == expected_size

    def test_chunk_empty_audio(self, provider: TtsProvider) -> None:
        chunks = provider.chunk_audio(b"")
        assert chunks == []

    def test_chunk_small_audio(self, provider: TtsProvider) -> None:
        """Audio smaller than chunk size returns single chunk."""
        small = b"\x00" * 100
        chunks = provider.chunk_audio(small)
        assert len(chunks) == 1
        assert chunks[0] == small

    def test_custom_chunk_size(self, mock_backend: MockTtsBackend) -> None:
        p = TtsProvider(backend=mock_backend, chunk_samples=1024)
        audio_bytes = b"\x00" * 10000
        chunks = p.chunk_audio(audio_bytes)
        for chunk in chunks[:-1]:
            assert len(chunk) == 1024 * 2


class TestTtsEventHandler:
    """Event handler protocol tests."""

    async def test_handle_describe(self, handler: TtsEventHandler) -> None:
        info = await handler.handle_describe()
        assert "tts" in info

    async def test_handle_synthesize(self, handler: TtsEventHandler) -> None:
        chunks = await handler.handle_synthesize("Hello world")
        assert len(chunks) > 0
        # Each chunk is bytes
        for chunk in chunks:
            assert isinstance(chunk, bytes)

    async def test_handle_synthesize_empty(self, handler: TtsEventHandler) -> None:
        chunks = await handler.handle_synthesize("")
        assert chunks == []

    async def test_handle_synthesize_with_voice(self, handler: TtsEventHandler) -> None:
        chunks = await handler.handle_synthesize("Hello", voice="bf_emma")
        assert len(chunks) > 0
