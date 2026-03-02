"""Voice pipeline data types — session, state, ASR/LLM/TTS results, metrics."""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray


class VoiceState(enum.Enum):
    """Voice pipeline state machine states."""

    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING_ASR = "processing_asr"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"


@dataclass
class ASRResult:
    """Speech-to-text transcription result."""

    text: str
    language: str = "en"
    confidence: float = 1.0
    duration_ms: float = 0.0  # time taken for ASR inference


@dataclass
class LLMChunk:
    """Single chunk of LLM streaming output."""

    text: str
    token_count: int = 1
    is_final: bool = False
    finish_reason: str | None = None  # "stop", "length", "tool_call"


@dataclass
class TTSChunk:
    """Audio chunk from TTS synthesis."""

    audio: NDArray[np.float32]
    sample_rate: int = 24000
    is_final: bool = False
    sentence_index: int = 0


@dataclass
class LatencyMetrics:
    """Timing measurements for a single voice interaction.

    All times in milliseconds. Measured at each pipeline stage.
    """

    # Timestamps (monotonic, ms)
    button_release_ts: float = 0.0
    asr_start_ts: float = 0.0
    asr_end_ts: float = 0.0
    llm_first_token_ts: float = 0.0
    llm_end_ts: float = 0.0
    tts_first_chunk_ts: float = 0.0
    first_audio_ts: float = 0.0  # speaker output begins

    @property
    def asr_latency_ms(self) -> float:
        """Button release → ASR text available."""
        return self.asr_end_ts - self.button_release_ts

    @property
    def llm_prefill_ms(self) -> float:
        """ASR complete → first LLM token."""
        return self.llm_first_token_ts - self.asr_end_ts

    @property
    def tts_chunk_ms(self) -> float:
        """First sentence text → audio chunk ready."""
        return self.tts_first_chunk_ts - self.llm_first_token_ts

    @property
    def ttfa_ms(self) -> float:
        """Time to first audio — button release → speaker plays."""
        return self.first_audio_ts - self.button_release_ts

    def as_dict(self) -> dict[str, float]:
        return {
            "asr_latency_ms": self.asr_latency_ms,
            "llm_prefill_ms": self.llm_prefill_ms,
            "tts_chunk_ms": self.tts_chunk_ms,
            "ttfa_ms": self.ttfa_ms,
        }


@dataclass
class VoiceSession:
    """Active voice conversation session."""

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    state: VoiceState = VoiceState.IDLE
    created_at: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)
    turn_count: int = 0
    history: list[dict[str, str]] = field(default_factory=list)  # [{"role": ..., "content": ...}]
    metrics: list[LatencyMetrics] = field(default_factory=list)

    @property
    def idle_seconds(self) -> float:
        return time.monotonic() - self.last_activity

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = time.monotonic()
