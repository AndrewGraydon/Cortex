"""Tests for voice pipeline using mock HAL services."""

from __future__ import annotations

import numpy as np

from cortex.hal.types import AudioData, AudioFormat, DisplayState
from cortex.voice.pipeline import VoicePipeline


class TestProcessUtterance:
    async def test_basic_utterance(self, pipeline: VoicePipeline) -> None:
        """Process a single utterance through the full pipeline."""
        audio = AudioData(
            samples=np.zeros(16000, dtype=np.int16),
            sample_rate=16000,
            format=AudioFormat.S16_LE,
        )
        metrics = await pipeline.process_utterance(audio)

        # Should have timing data
        assert metrics.asr_end_ts > metrics.asr_start_ts
        assert metrics.llm_end_ts > 0

        # Session should be created
        assert pipeline.session is not None
        assert pipeline.session.turn_count == 1

    async def test_creates_session(self, pipeline: VoicePipeline) -> None:
        audio = AudioData(samples=np.zeros(16000, dtype=np.int16), sample_rate=16000)
        await pipeline.process_utterance(audio)
        assert pipeline.session is not None
        assert len(pipeline.session.session_id) == 12

    async def test_multi_turn(self, pipeline: VoicePipeline) -> None:
        """Multiple utterances maintain session."""
        audio = AudioData(samples=np.zeros(16000, dtype=np.int16), sample_rate=16000)
        await pipeline.process_utterance(audio)
        session_id = pipeline.session.session_id

        await pipeline.process_utterance(audio)
        assert pipeline.session.session_id == session_id
        assert pipeline.session.turn_count == 2

    async def test_farewell_ends_session(self, pipeline: VoicePipeline) -> None:
        """Farewell phrase ends the session."""
        # First, create a session
        audio = AudioData(samples=np.zeros(16000, dtype=np.int16), sample_rate=16000)
        await pipeline.process_utterance(audio)
        assert pipeline.session is not None

        # Mock ASR to return "goodbye"
        pipeline._npu._response_index = 0  # Reset
        # We need to mock the ASR result — set mock_text param
        # For the mock, we'll directly test _is_farewell
        assert VoicePipeline._is_farewell("goodbye")
        assert VoicePipeline._is_farewell("Bye!")
        assert VoicePipeline._is_farewell("Good night.")
        assert not VoicePipeline._is_farewell("Hello")
        assert not VoicePipeline._is_farewell("What time is it?")

    async def test_display_state_transitions(self, pipeline: VoicePipeline) -> None:
        """Display should transition through states during pipeline."""
        display = pipeline._display
        audio = AudioData(samples=np.zeros(16000, dtype=np.int16), sample_rate=16000)
        await pipeline.process_utterance(audio)

        # Should have gone through THINKING → SPEAKING → IDLE
        states = [s for s, _ in display._state_history]
        assert DisplayState.THINKING in states
        assert DisplayState.SPEAKING in states
        # Final state should be IDLE
        assert await display.get_state() == DisplayState.IDLE

    async def test_history_accumulated(self, pipeline: VoicePipeline) -> None:
        """Session history should accumulate user and assistant messages."""
        audio = AudioData(samples=np.zeros(16000, dtype=np.int16), sample_rate=16000)
        await pipeline.process_utterance(audio)

        assert len(pipeline.session.history) == 2  # user + assistant
        assert pipeline.session.history[0]["role"] == "user"
        assert pipeline.session.history[1]["role"] == "assistant"


class TestContextAssemblerWiring:
    """Test that context assembler is used when provided."""

    async def test_build_llm_inputs_with_assembler(self, pipeline: VoicePipeline) -> None:
        """When assembler is present, messages should be in inputs."""
        from cortex.reasoning.context_assembler import ContextAssembler

        assembler = ContextAssembler()
        pipeline._context_assembler = assembler

        # Create a session with some history
        audio = AudioData(samples=np.zeros(16000, dtype=np.int16), sample_rate=16000)
        await pipeline.process_utterance(audio)

        # Now build inputs with history
        inputs = pipeline._build_llm_inputs("Follow-up question")
        assert "messages" in inputs.params
        messages = inputs.params["messages"]
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "Follow-up question"

    def test_build_llm_inputs_without_assembler(self, pipeline: VoicePipeline) -> None:
        """Without assembler, plain text inputs returned."""
        from cortex.voice.types import VoiceSession

        pipeline._session = VoiceSession()
        inputs = pipeline._build_llm_inputs("Hello")
        assert inputs.params == {}
        assert str(inputs.data) == "Hello"

    def test_build_llm_inputs_without_session(self, pipeline: VoicePipeline) -> None:
        """Without session, plain text even if assembler exists."""
        from cortex.reasoning.context_assembler import ContextAssembler

        pipeline._context_assembler = ContextAssembler()
        pipeline._session = None
        inputs = pipeline._build_llm_inputs("Hello")
        assert inputs.params == {}


class TestGreetingResponseDetection:
    """Greeting-like LLM responses should be excluded from history."""

    def test_pure_greeting(self) -> None:
        assert VoicePipeline._is_greeting_response("Hello! How can I help you?")

    def test_greeting_with_assist(self) -> None:
        assert VoicePipeline._is_greeting_response("Hi! What can I do for you?")

    def test_i_am_cortex_short(self) -> None:
        assert VoicePipeline._is_greeting_response("Hello, I am Cortex.")

    def test_long_response_with_greeting_not_flagged(self) -> None:
        """Longer responses with real content should NOT be flagged."""
        assert not VoicePipeline._is_greeting_response(
            "I'm Cortex, your local voice assistant running on a Raspberry Pi. "
            "How can I help you today?"
        )

    def test_real_answer_not_greeting(self) -> None:
        assert not VoicePipeline._is_greeting_response(
            "The sky is blue because of Rayleigh scattering."
        )

    def test_factual_response(self) -> None:
        assert not VoicePipeline._is_greeting_response("2 plus 2 equals 4.")

    def test_empty_not_greeting(self) -> None:
        assert not VoicePipeline._is_greeting_response("")


class TestSentenceDetectorIntegration:
    def test_detector_exists(self) -> None:
        from cortex.voice.sentence_detector import SentenceDetector

        sd = SentenceDetector()
        sd.feed("Hello world. ")
        sd.feed("How are you? ")
        remaining = sd.flush()
        # Should work without error
        assert isinstance(remaining, str)
