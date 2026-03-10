"""Shared fixtures for soak/fault-injection tests.

Provides a full system context with mock services, circuit breakers,
degradation engine, and health monitor wired together.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from cortex.hal.audio.mock import MockAudioService
from cortex.hal.display.mock import MockButtonService, MockDisplayService
from cortex.hal.npu.mock import MockNpuService
from cortex.hal.types import AudioData, AudioFormat
from cortex.resilience.circuit_breaker import CircuitBreaker
from cortex.resilience.degradation import DegradationEngine, DegradationState
from cortex.voice.pipeline import VoicePipeline


class SystemContext:
    """Full system context for fault injection testing.

    Bundles mock services, circuit breakers, and degradation engine
    into a single test fixture.
    """

    def __init__(
        self,
        npu: MockNpuService,
        audio: MockAudioService,
        display: MockDisplayService,
        button: MockButtonService,
        pipeline: VoicePipeline,
        breakers: dict[str, CircuitBreaker],
        engine: DegradationEngine,
    ) -> None:
        self.npu = npu
        self.audio = audio
        self.display = display
        self.button = button
        self.pipeline = pipeline
        self.breakers = breakers
        self.engine = engine
        self.state_changes: list[DegradationState] = []

    def evaluate(self, **kwargs: Any) -> DegradationState:
        """Evaluate degradation with current breakers + kwargs."""
        return self.engine.evaluate(breakers=self.breakers, **kwargs)


@pytest.fixture
async def system_context() -> SystemContext:
    """Full system context with mock services and resilience infrastructure."""
    npu = MockNpuService()
    await npu.load_model("sensevoice", Path("/mock/sensevoice"))
    await npu.load_model("qwen3-vl-2b", Path("/mock/qwen3vl"))
    await npu.load_model("kokoro", Path("/mock/kokoro"))

    audio = MockAudioService()
    display = MockDisplayService()
    button = MockButtonService()

    pipe = VoicePipeline(npu=npu, audio=audio, display=display, button=button)
    asr_handle = npu._loaded_models["sensevoice"]
    llm_handle = npu._loaded_models["qwen3-vl-2b"]
    tts_handle = npu._loaded_models["kokoro"]
    pipe.set_handles(asr=asr_handle, llm=llm_handle, tts=tts_handle)

    breakers = {
        "llm": CircuitBreaker("llm", failure_threshold=3, recovery_timeout_s=0.5),
        "tts": CircuitBreaker("tts", failure_threshold=3, recovery_timeout_s=0.5),
        "asr": CircuitBreaker("asr", failure_threshold=3, recovery_timeout_s=0.5),
    }

    engine = DegradationEngine()
    ctx = SystemContext(
        npu=npu,
        audio=audio,
        display=display,
        button=button,
        pipeline=pipe,
        breakers=breakers,
        engine=engine,
    )
    engine.on_change(lambda state: ctx.state_changes.append(state))
    return ctx


@pytest.fixture
def silence_1s() -> AudioData:
    """1 second of silence at 16kHz."""
    return AudioData(
        samples=np.zeros(16000, dtype=np.int16),
        sample_rate=16000,
        format=AudioFormat.S16_LE,
    )
