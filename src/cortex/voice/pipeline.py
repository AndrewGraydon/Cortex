"""Voice pipeline — button press → ASR → LLM → TTS → speaker.

Orchestrates the full voice interaction loop using HAL services.
Supports both sequential and streaming modes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import numpy as np

from cortex.hal.types import (
    AudioData,
    AudioFormat,
    ButtonGesture,
    DisplayState,
    InferenceInputs,
    ModelHandle,
)
from cortex.voice.sentence_detector import SentenceDetector
from cortex.voice.types import (
    ASRResult,
    LatencyMetrics,
    VoiceSession,
)

logger = logging.getLogger(__name__)

# Farewell patterns — end session without LLM call
FAREWELL_PATTERNS = {
    "goodbye",
    "bye",
    "good night",
    "see you",
    "that's all",
    "thanks bye",
    "thank you bye",
    "stop",
    "quit",
    "exit",
}

# Session timeouts
SESSION_IDLE_TIMEOUT_S = 300.0  # 5 minutes
CROSSFADE_SAMPLES = 240  # 10ms at 24kHz
LLM_MAX_RETRIES = 1  # Retry LLM once on failure


class VoicePipeline:
    """Main voice interaction pipeline.

    Coordinates button events, ASR, LLM, TTS, and audio playback.
    Uses Protocol-typed HAL services for hardware abstraction.
    """

    def __init__(
        self,
        npu: Any,
        audio: Any,
        display: Any,
        button: Any,
        system_prompt: str = "You are Cortex, a helpful voice assistant. Be concise.",
    ) -> None:
        self._npu = npu
        self._audio = audio
        self._display = display
        self._button = button
        self._system_prompt = system_prompt

        # Model handles (set after loading)
        self._asr_handle: ModelHandle | None = None
        self._llm_handle: ModelHandle | None = None
        self._tts_handle: ModelHandle | None = None

        # Session state
        self._session: VoiceSession | None = None
        self._running = False
        self._sentence_detector = SentenceDetector()

    @property
    def session(self) -> VoiceSession | None:
        return self._session

    def set_handles(
        self,
        asr: ModelHandle,
        llm: ModelHandle,
        tts: ModelHandle,
    ) -> None:
        """Set model handles after loading."""
        self._asr_handle = asr
        self._llm_handle = llm
        self._tts_handle = tts

    async def run(self) -> None:
        """Main pipeline loop — listen for button gestures and handle voice."""
        self._running = True
        logger.info("Voice pipeline started")

        try:
            async for event in self._button.subscribe():
                if not self._running:
                    break

                if event.gesture == ButtonGesture.HOLD_START:
                    await self._handle_hold_start()
                elif event.gesture == ButtonGesture.HOLD_END:
                    await self._handle_hold_end()
                elif event.gesture == ButtonGesture.LONG_PRESS:
                    await self._handle_long_press()
                elif event.gesture == ButtonGesture.SINGLE_CLICK:
                    pass  # Approve (Phase 2)
                elif event.gesture == ButtonGesture.DOUBLE_CLICK:
                    pass  # Camera capture (Phase 2)
                elif event.gesture == ButtonGesture.TRIPLE_CLICK:
                    pass  # System menu (Phase 2)
        finally:
            self._running = False
            logger.info("Voice pipeline stopped")

    async def stop(self) -> None:
        """Stop the pipeline."""
        self._running = False
        await self._audio.stop_playback()

    async def process_utterance(self, audio_data: AudioData) -> LatencyMetrics:
        """Process a single voice utterance through the full pipeline.

        This is the core method — ASR → LLM → TTS → playback.
        Returns latency metrics for the interaction.
        Always returns to IDLE display state, even on early exit or error.
        """
        metrics = LatencyMetrics()
        metrics.button_release_ts = _now_ms()

        # Ensure session exists
        if self._session is None:
            self._session = VoiceSession()
            logger.info("New session: %s", self._session.session_id)

        self._session.touch()

        try:
            # --- ASR ---
            await self._display.set_state(DisplayState.THINKING, "Processing...")
            metrics.asr_start_ts = _now_ms()
            asr_result = await self._run_asr(audio_data)
            metrics.asr_end_ts = _now_ms()

            logger.info(
                "ASR: '%s' (%.0fms)",
                asr_result.text,
                metrics.asr_end_ts - metrics.asr_start_ts,
            )

            if not asr_result.text.strip():
                await self._speak("I didn't catch that. Could you try again?", metrics)
                return metrics

            # Check for farewell
            if self._is_farewell(asr_result.text):
                await self._speak("Goodbye!", metrics)
                self._session = None
                return metrics

            # Add user message to history
            self._session.history.append({"role": "user", "content": asr_result.text})

            # --- LLM → TTS (streaming) ---
            await self._display.set_state(DisplayState.THINKING, "Thinking...")
            response_text = await self._run_llm_with_retry(asr_result.text, metrics)

            # Add assistant response to history
            if response_text:
                self._session.history.append({"role": "assistant", "content": response_text})

            self._session.turn_count += 1
            self._session.metrics.append(metrics)

            # Check session timeout
            if self._session.idle_seconds > SESSION_IDLE_TIMEOUT_S:
                logger.info("Session timed out")
                self._session = None

        except Exception:
            logger.exception("Pipeline error")
            await self._display.set_state(DisplayState.ERROR, "Something went wrong")
            await asyncio.sleep(2.0)
        finally:
            await self._display.set_state(DisplayState.IDLE)

        return metrics

    # --- Internal handlers ---

    async def _handle_hold_start(self) -> None:
        """Start recording on button hold."""
        # Stop any current playback
        await self._audio.stop_playback()
        await self._display.set_state(DisplayState.LISTENING, "Listening...")
        await self._audio.start_capture(sample_rate=16000)

    async def _handle_hold_end(self) -> None:
        """Stop recording and process the utterance."""
        audio_data = await self._audio.stop_capture()
        await self.process_utterance(audio_data)

    async def _handle_long_press(self) -> None:
        """Stop TTS playback (interruption)."""
        await self._audio.stop_playback()
        await self._display.set_state(DisplayState.IDLE)

    # --- Pipeline stages ---

    async def _run_asr(self, audio_data: AudioData) -> ASRResult:
        """Run ASR inference on captured audio."""
        assert self._asr_handle is not None

        result = await self._npu.infer(
            self._asr_handle,
            InferenceInputs(
                data=audio_data.samples,
                params={"language": "auto", "sample_rate": audio_data.sample_rate},
            ),
        )
        return ASRResult(
            text=str(result.data),
            language=result.metadata.get("language", "en"),
        )

    async def _run_llm_with_retry(self, user_text: str, metrics: LatencyMetrics) -> str:
        """Run LLM → TTS streaming with retry on LLM failure."""
        for attempt in range(LLM_MAX_RETRIES + 1):
            try:
                return await self._run_llm_tts_streaming(user_text, metrics)
            except Exception:
                if attempt < LLM_MAX_RETRIES:
                    logger.warning("LLM failed (attempt %d), retrying...", attempt + 1)
                    await asyncio.sleep(0.5)
                else:
                    logger.exception("LLM failed after %d retries", LLM_MAX_RETRIES + 1)
                    apology = "Sorry, I'm having trouble thinking right now. Please try again."
                    await self._speak(apology, metrics)
                    return apology
        return ""  # unreachable, satisfies mypy

    async def _run_llm_tts_streaming(self, user_text: str, metrics: LatencyMetrics) -> str:
        """Stream LLM → sentence detect → TTS → playback."""
        assert self._llm_handle is not None
        assert self._tts_handle is not None

        full_response = ""
        first_token = True
        self._sentence_detector.reset()

        async for chunk in self._npu.infer_stream(
            self._llm_handle, InferenceInputs(data=user_text)
        ):
            token_text = str(chunk.data)
            full_response += token_text

            if first_token:
                metrics.llm_first_token_ts = _now_ms()
                first_token = False

            # Feed tokens to sentence detector
            sentences = self._sentence_detector.feed(token_text)
            for sentence in sentences:
                await self._synthesize_and_play(sentence, metrics)

        # Flush any remaining text
        remaining = self._sentence_detector.flush()
        if remaining:
            await self._synthesize_and_play(remaining, metrics)

        metrics.llm_end_ts = _now_ms()

        log_metrics = {
            "asr_ms": f"{metrics.asr_latency_ms:.0f}",
            "prefill_ms": f"{metrics.llm_prefill_ms:.0f}",
            "ttfa_ms": f"{metrics.ttfa_ms:.0f}",
        }
        logger.info("Metrics: %s", log_metrics)

        return full_response

    async def _synthesize_and_play(self, text: str, metrics: LatencyMetrics) -> None:
        """TTS a sentence and play it. Falls back to LCD text if TTS fails."""
        assert self._tts_handle is not None

        try:
            result = await self._npu.infer(
                self._tts_handle,
                InferenceInputs(data=text),
            )
        except Exception:
            logger.warning("TTS failed, falling back to LCD text: %s", text)
            await self._display.set_state(DisplayState.SPEAKING, text)
            await asyncio.sleep(max(1.0, len(text.split()) * 0.3))
            return

        if metrics.tts_first_chunk_ts == 0.0:
            metrics.tts_first_chunk_ts = _now_ms()

        audio_array = result.data
        if isinstance(audio_array, np.ndarray) and len(audio_array) > 0:
            # Convert float32 to int16 for playback
            samples = (audio_array * 32767).clip(-32768, 32767).astype(np.int16)

            await self._display.set_state(DisplayState.SPEAKING, text)

            if metrics.first_audio_ts == 0.0:
                metrics.first_audio_ts = _now_ms()

            await self._audio.play(
                AudioData(
                    samples=samples,
                    sample_rate=result.metadata.get("sample_rate", 24000),
                    format=AudioFormat.S16_LE,
                )
            )

    async def _speak(self, text: str, metrics: LatencyMetrics) -> None:
        """Synthesize and play a simple text response."""
        await self._display.set_state(DisplayState.SPEAKING, text)
        await self._synthesize_and_play(text, metrics)

    @staticmethod
    def _is_farewell(text: str) -> bool:
        """Check if text is a farewell phrase."""
        normalized = text.lower().strip().rstrip(".!?")
        return normalized in FAREWELL_PATTERNS


def _now_ms() -> float:
    """Current time in milliseconds (monotonic)."""
    return time.monotonic() * 1000
