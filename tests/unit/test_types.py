"""Tests for HAL and voice data types."""

from __future__ import annotations

import numpy as np

from cortex.hal.types import (
    AudioData,
    AudioFormat,
    ButtonEvent,
    ButtonGesture,
    DisplayState,
    InferenceInputs,
    InferenceOutputs,
    LedColor,
    ModelHandle,
    NpuCapabilities,
    NpuStatus,
)
from cortex.voice.types import (
    ASRResult,
    LatencyMetrics,
    LLMChunk,
    TTSChunk,
    VoiceSession,
    VoiceState,
)


class TestModelHandle:
    def test_frozen(self) -> None:
        h = ModelHandle(model_id="qwen3-1.7b")
        assert h.model_id == "qwen3-1.7b"

    def test_equality_by_model_id(self) -> None:
        h1 = ModelHandle(model_id="sensevoice")
        h2 = ModelHandle(model_id="sensevoice")
        assert h1 == h2

    def test_internal_not_in_repr(self) -> None:
        h = ModelHandle(model_id="kokoro", _internal={"ptr": 0xDEAD})
        assert "0xDEAD" not in repr(h)
        assert "ptr" not in repr(h)


class TestInferenceIO:
    def test_string_input(self) -> None:
        inp = InferenceInputs(data="Hello world")
        assert isinstance(inp.data, str)

    def test_numpy_input(self) -> None:
        arr = np.zeros(16000, dtype=np.int16)
        inp = InferenceInputs(data=arr, params={"sample_rate": 16000})
        assert inp.params["sample_rate"] == 16000

    def test_output_with_metadata(self) -> None:
        out = InferenceOutputs(data="Hello", metadata={"tokens": 1})
        assert out.metadata["tokens"] == 1


class TestNpuStatus:
    def test_npu_status(self) -> None:
        s = NpuStatus(
            temperature_c=62.0,
            memory_used_mb=4950,
            memory_total_mb=7040,
            models_loaded=["sensevoice", "qwen3-1.7b"],
        )
        assert s.temperature_c == 62.0
        assert len(s.models_loaded) == 2

    def test_npu_capabilities(self) -> None:
        c = NpuCapabilities(total_memory_mb=7040, compute_tops=14.4)
        assert c.total_memory_mb == 7040
        assert "axmodel" in c.supported_formats


class TestAudioData:
    def test_s16_audio(self) -> None:
        samples = np.zeros(16000, dtype=np.int16)
        audio = AudioData(samples=samples, sample_rate=16000)
        assert audio.format == AudioFormat.S16_LE
        assert audio.channels == 1

    def test_float32_audio(self) -> None:
        samples = np.zeros(24000, dtype=np.float32)
        audio = AudioData(samples=samples, sample_rate=24000, format=AudioFormat.FLOAT32)
        assert audio.format == AudioFormat.FLOAT32


class TestDisplayState:
    def test_all_states_exist(self) -> None:
        expected = {"idle", "listening", "thinking", "speaking", "alert", "error"}
        actual = {s.value for s in DisplayState}
        assert actual == expected


class TestLedColor:
    def test_preset_colors(self) -> None:
        assert LedColor.idle() == LedColor(0, 0, 85)
        assert LedColor.listening() == LedColor(0, 255, 0)
        assert LedColor.error() == LedColor(255, 0, 0)
        assert LedColor.off() == LedColor(0, 0, 0)

    def test_frozen(self) -> None:
        c = LedColor(255, 0, 0)
        assert c.r == 255


class TestButtonTypes:
    def test_all_gestures(self) -> None:
        expected = {
            "hold_start",
            "hold_end",
            "single_click",
            "double_click",
            "long_press",
            "triple_click",
        }
        actual = {g.value for g in ButtonGesture}
        assert actual == expected

    def test_button_event(self) -> None:
        evt = ButtonEvent(gesture=ButtonGesture.HOLD_START, timestamp=1000.0)
        assert evt.gesture == ButtonGesture.HOLD_START
        assert evt.duration_ms == 0.0


class TestVoiceState:
    def test_all_states(self) -> None:
        expected = {"idle", "listening", "processing_asr", "thinking", "speaking", "error"}
        actual = {s.value for s in VoiceState}
        assert actual == expected


class TestASRResult:
    def test_defaults(self) -> None:
        r = ASRResult(text="Hello world")
        assert r.confidence == 1.0
        assert r.language == "en"


class TestLLMChunk:
    def test_streaming_chunk(self) -> None:
        c = LLMChunk(text="Hello", token_count=1, is_final=False)
        assert not c.is_final


class TestTTSChunk:
    def test_audio_chunk(self) -> None:
        audio = np.zeros(2400, dtype=np.float32)
        c = TTSChunk(audio=audio, sample_rate=24000, sentence_index=0)
        assert c.sample_rate == 24000
        assert len(c.audio) == 2400


class TestLatencyMetrics:
    def test_computed_properties(self) -> None:
        m = LatencyMetrics(
            button_release_ts=1000.0,
            asr_start_ts=1000.0,
            asr_end_ts=1400.0,
            llm_first_token_ts=1900.0,
            llm_end_ts=3500.0,
            tts_first_chunk_ts=2200.0,
            first_audio_ts=2300.0,
        )
        assert m.asr_latency_ms == 400.0
        assert m.llm_prefill_ms == 500.0
        assert m.tts_chunk_ms == 300.0
        assert m.ttfa_ms == 1300.0

    def test_as_dict(self) -> None:
        m = LatencyMetrics(
            button_release_ts=0.0,
            asr_end_ts=400.0,
            llm_first_token_ts=900.0,
            tts_first_chunk_ts=1200.0,
            first_audio_ts=1300.0,
        )
        d = m.as_dict()
        assert "ttfa_ms" in d
        assert d["ttfa_ms"] == 1300.0


class TestVoiceSession:
    def test_session_creation(self) -> None:
        s = VoiceSession()
        assert s.state == VoiceState.IDLE
        assert s.turn_count == 0
        assert len(s.session_id) == 12

    def test_touch_updates_activity(self) -> None:
        s = VoiceSession()
        old = s.last_activity
        s.touch()
        assert s.last_activity >= old

    def test_history(self) -> None:
        s = VoiceSession()
        s.history.append({"role": "user", "content": "Hello"})
        s.history.append({"role": "assistant", "content": "Hi there"})
        assert len(s.history) == 2
