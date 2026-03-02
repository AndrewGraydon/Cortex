"""Tests for MockAudioService and AudioService Protocol compliance."""

from __future__ import annotations

from collections.abc import AsyncIterator

import numpy as np
import pytest

from cortex.hal.audio.mock import MockAudioService
from cortex.hal.types import AudioData, AudioFormat


@pytest.fixture
def mock_audio() -> MockAudioService:
    return MockAudioService()


class TestCaptureLifecycle:
    async def test_start_stop_capture(self, mock_audio: MockAudioService) -> None:
        await mock_audio.start_capture(16000)
        assert mock_audio.is_capturing
        result = await mock_audio.stop_capture()
        assert not mock_audio.is_capturing
        assert result.sample_rate == 16000
        assert result.channels == 1

    async def test_capture_returns_mock_audio(self, mock_audio: MockAudioService) -> None:
        fake_audio = np.ones(8000, dtype=np.int16) * 100
        mock_audio.set_mock_capture(fake_audio, sample_rate=16000)
        await mock_audio.start_capture(16000)
        result = await mock_audio.stop_capture()
        np.testing.assert_array_equal(result.samples, fake_audio)

    async def test_capture_default_silence(self, mock_audio: MockAudioService) -> None:
        await mock_audio.start_capture(16000)
        result = await mock_audio.stop_capture()
        assert len(result.samples) == 16000
        assert np.all(result.samples == 0)

    async def test_double_start_raises(self, mock_audio: MockAudioService) -> None:
        await mock_audio.start_capture()
        with pytest.raises(RuntimeError, match="Already capturing"):
            await mock_audio.start_capture()
        await mock_audio.stop_capture()

    async def test_stop_without_start_raises(self, mock_audio: MockAudioService) -> None:
        with pytest.raises(RuntimeError, match="Not capturing"):
            await mock_audio.stop_capture()


class TestPlayback:
    async def test_play_audio(self, mock_audio: MockAudioService) -> None:
        audio = AudioData(
            samples=np.zeros(24000, dtype=np.int16),
            sample_rate=24000,
            channels=1,
            format=AudioFormat.S16_LE,
        )
        await mock_audio.play(audio)
        assert len(mock_audio._played_audio) == 1
        assert mock_audio._played_audio[0].sample_rate == 24000

    async def test_play_stream(self, mock_audio: MockAudioService) -> None:
        async def chunk_generator() -> AsyncIterator[AudioData]:
            for _ in range(3):
                yield AudioData(
                    samples=np.zeros(2400, dtype=np.int16),
                    sample_rate=24000,
                )

        await mock_audio.play_stream(chunk_generator())
        assert len(mock_audio._played_audio) == 3

    async def test_stop_playback(self, mock_audio: MockAudioService) -> None:
        await mock_audio.stop_playback()
        assert not mock_audio.is_playing


class TestOperationLog:
    async def test_operations_recorded(self, mock_audio: MockAudioService) -> None:
        await mock_audio.start_capture(16000)
        await mock_audio.stop_capture()
        audio = AudioData(samples=np.zeros(100, dtype=np.int16), sample_rate=24000)
        await mock_audio.play(audio)
        assert "start_capture(16000)" in mock_audio._operations
        assert "stop_capture" in mock_audio._operations
        assert "play(100 samples)" in mock_audio._operations
