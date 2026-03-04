"""Tests for voice pipeline error recovery paths."""

from __future__ import annotations

import numpy as np

from cortex.hal.npu.mock import MockError
from cortex.hal.types import AudioData, DisplayState
from cortex.voice.pipeline import VoicePipeline


def _make_audio() -> AudioData:
    return AudioData(samples=np.zeros(16000, dtype=np.int16), sample_rate=16000)


class TestEmptyASR:
    async def test_empty_asr_responds(self, pipeline: VoicePipeline) -> None:
        """Empty ASR text triggers 'didn't catch that' response."""
        # Mock ASR to return empty text
        pipeline._npu._errors.clear()
        # Inject empty mock_text via params — mock ASR reads mock_text param
        original_asr = pipeline._npu._mock_asr

        async def empty_asr(inputs: ...) -> ...:
            result = await original_asr(inputs)
            result.data = ""
            return result

        pipeline._npu._mock_asr = empty_asr  # type: ignore[assignment]

        audio = _make_audio()
        metrics = await pipeline.process_utterance(audio)

        # Should still return metrics (pipeline didn't crash)
        assert metrics.asr_end_ts > metrics.asr_start_ts

        # Display should end at IDLE
        display = pipeline._display
        assert await display.get_state() == DisplayState.IDLE


class TestLLMRetry:
    async def test_llm_retries_on_failure(self, pipeline: VoicePipeline) -> None:
        """LLM retry should succeed on second attempt."""
        npu = pipeline._npu
        # Inject one inference error for LLM — will be consumed on first attempt
        npu.inject_error(
            MockError(model_id="qwen3-vl-2b", error_type="inference_error", message="LLM timeout")
        )

        audio = _make_audio()
        await pipeline.process_utterance(audio)

        # Should have completed (retry succeeded)
        assert pipeline.session is not None
        assert pipeline.session.turn_count == 1

    async def test_llm_apologizes_after_exhausted_retries(self, pipeline: VoicePipeline) -> None:
        """After all retries fail, pipeline should apologize."""
        npu = pipeline._npu
        # Inject TWO errors — first attempt + retry both fail
        npu.inject_error(
            MockError(model_id="qwen3-vl-2b", error_type="inference_error", message="LLM fail 1")
        )
        npu.inject_error(
            MockError(model_id="qwen3-vl-2b", error_type="inference_error", message="LLM fail 2")
        )

        audio = _make_audio()
        await pipeline.process_utterance(audio)

        # Session should exist (turn still counted)
        assert pipeline.session is not None
        # The apology should be in the assistant history
        assistant_msgs = [m for m in pipeline.session.history if m["role"] == "assistant"]
        assert any("trouble" in m["content"] for m in assistant_msgs)


class TestTTSFallback:
    async def test_tts_failure_shows_text_on_display(self, pipeline: VoicePipeline) -> None:
        """When TTS fails, text should be shown on LCD as fallback."""
        npu = pipeline._npu
        # Inject TTS error
        npu.inject_error(
            MockError(model_id="kokoro", error_type="inference_error", message="TTS failed")
        )

        audio = _make_audio()
        await pipeline.process_utterance(audio)

        # Pipeline should complete without crash
        display = pipeline._display
        assert await display.get_state() == DisplayState.IDLE

        # Display should have shown SPEAKING state (text fallback)
        states = [s for s, _ in display._state_history]
        assert DisplayState.SPEAKING in states


class TestPipelineError:
    async def test_generic_error_shows_error_state(self, pipeline: VoicePipeline) -> None:
        """Unhandled errors should show ERROR state on display."""
        # Inject ASR error — not caught by specific handlers
        npu = pipeline._npu
        npu.inject_error(
            MockError(
                model_id="sensevoice",
                error_type="inference_error",
                message="ASR crashed",
            )
        )

        audio = _make_audio()
        await pipeline.process_utterance(audio)

        display = pipeline._display
        states = [s for s, _ in display._state_history]
        assert DisplayState.ERROR in states
        # Should recover to IDLE
        assert await display.get_state() == DisplayState.IDLE
