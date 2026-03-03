"""Tests for voice pipeline interruption handling."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cortex.hal.audio.mock import MockAudioService
from cortex.hal.display.mock import MockButtonService, MockDisplayService
from cortex.hal.npu.mock import MockNpuService
from cortex.hal.types import AudioData, DisplayState
from cortex.voice.pipeline import VoicePipeline


@pytest.fixture
async def pipeline() -> VoicePipeline:
    """Create a fully wired voice pipeline with mock services."""
    npu = MockNpuService()
    audio = MockAudioService()
    display = MockDisplayService()
    button = MockButtonService()

    asr_handle = await npu.load_model("sensevoice", Path("/mock/sensevoice"))
    llm_handle = await npu.load_model("qwen3-1.7b", Path("/mock/qwen3"))
    tts_handle = await npu.load_model("kokoro", Path("/mock/kokoro"))

    pipe = VoicePipeline(npu=npu, audio=audio, display=display, button=button)
    pipe.set_handles(asr=asr_handle, llm=llm_handle, tts=tts_handle)
    return pipe


class TestLongPressInterruption:
    async def test_long_press_stops_playback(self, pipeline: VoicePipeline) -> None:
        """Long press should stop audio playback."""
        # Simulate some playback state
        await pipeline._display.set_state(DisplayState.SPEAKING, "talking...")

        await pipeline._handle_long_press()

        display = pipeline._display
        assert await display.get_state() == DisplayState.IDLE

    async def test_long_press_calls_stop_playback(self, pipeline: VoicePipeline) -> None:
        """Long press should call stop_playback on audio service."""
        audio = pipeline._audio
        await pipeline._handle_long_press()

        # MockAudioService records operations as strings
        assert "stop_playback" in audio._operations


class TestHoldStartInterruption:
    async def test_hold_start_stops_current_playback(self, pipeline: VoicePipeline) -> None:
        """Starting a new hold should stop any current playback first."""
        await pipeline._handle_hold_start()

        audio = pipeline._audio
        display = pipeline._display

        # Audio operations are strings like "stop_playback", "start_capture(16000)"
        assert "stop_playback" in audio._operations
        start_caps = [op for op in audio._operations if op.startswith("start_capture")]
        assert len(start_caps) > 0
        # stop_playback comes before start_capture
        stop_idx = audio._operations.index("stop_playback")
        start_idx = next(
            i for i, op in enumerate(audio._operations) if op.startswith("start_capture")
        )
        assert stop_idx < start_idx

        # Display should show LISTENING
        assert await display.get_state() == DisplayState.LISTENING


class TestSessionManagement:
    async def test_session_created_on_first_utterance(self, pipeline: VoicePipeline) -> None:
        """Session should be created on first utterance."""
        assert pipeline.session is None

        audio = AudioData(samples=np.zeros(16000, dtype=np.int16), sample_rate=16000)
        await pipeline.process_utterance(audio)

        assert pipeline.session is not None
        assert len(pipeline.session.session_id) == 12

    async def test_farewell_ends_session(self, pipeline: VoicePipeline) -> None:
        """Farewell detection should work correctly."""
        assert VoicePipeline._is_farewell("goodbye")
        assert VoicePipeline._is_farewell("Bye!")
        assert VoicePipeline._is_farewell("Good night.")
        assert VoicePipeline._is_farewell("STOP")
        assert VoicePipeline._is_farewell("exit")
        assert not VoicePipeline._is_farewell("Hello")
        assert not VoicePipeline._is_farewell("What time is it?")
        assert not VoicePipeline._is_farewell("Tell me about goodbyes")

    async def test_session_persists_across_turns(self, pipeline: VoicePipeline) -> None:
        """Session should persist across multiple turns."""
        audio = AudioData(samples=np.zeros(16000, dtype=np.int16), sample_rate=16000)

        await pipeline.process_utterance(audio)
        session_id = pipeline.session.session_id
        assert pipeline.session.turn_count == 1

        await pipeline.process_utterance(audio)
        assert pipeline.session.session_id == session_id
        assert pipeline.session.turn_count == 2

    async def test_history_grows_with_turns(self, pipeline: VoicePipeline) -> None:
        """Session history should accumulate user + assistant messages."""
        audio = AudioData(samples=np.zeros(16000, dtype=np.int16), sample_rate=16000)

        await pipeline.process_utterance(audio)
        assert len(pipeline.session.history) == 2  # user + assistant

        await pipeline.process_utterance(audio)
        assert len(pipeline.session.history) == 4  # 2 * (user + assistant)

    async def test_metrics_accumulated(self, pipeline: VoicePipeline) -> None:
        """Metrics should be accumulated per turn."""
        audio = AudioData(samples=np.zeros(16000, dtype=np.int16), sample_rate=16000)

        await pipeline.process_utterance(audio)
        assert len(pipeline.session.metrics) == 1

        await pipeline.process_utterance(audio)
        assert len(pipeline.session.metrics) == 2
