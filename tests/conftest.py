"""Shared test fixtures for Cortex test suite."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cortex.hal.audio.mock import MockAudioService
from cortex.hal.display.mock import MockButtonService, MockDisplayService
from cortex.hal.npu.mock import MockNpuService
from cortex.hal.types import AudioData, AudioFormat
from cortex.voice.pipeline import VoicePipeline


@pytest.fixture
async def mock_npu() -> MockNpuService:
    """MockNpuService with all models pre-loaded."""
    npu = MockNpuService()
    await npu.load_model("sensevoice", Path("/mock/sensevoice"))
    await npu.load_model("qwen3-vl-2b", Path("/mock/qwen3vl"))
    await npu.load_model("kokoro", Path("/mock/kokoro"))
    return npu


@pytest.fixture
def mock_audio() -> MockAudioService:
    return MockAudioService()


@pytest.fixture
def mock_display() -> MockDisplayService:
    return MockDisplayService()


@pytest.fixture
def mock_button() -> MockButtonService:
    return MockButtonService()


@pytest.fixture
async def pipeline(
    mock_npu: MockNpuService,
    mock_audio: MockAudioService,
    mock_display: MockDisplayService,
    mock_button: MockButtonService,
) -> VoicePipeline:
    """Fully wired voice pipeline with mock services."""
    pipe = VoicePipeline(
        npu=mock_npu,
        audio=mock_audio,
        display=mock_display,
        button=mock_button,
    )
    # Get the handles from already-loaded models
    asr_handle = mock_npu._loaded_models["sensevoice"]
    llm_handle = mock_npu._loaded_models["qwen3-vl-2b"]
    tts_handle = mock_npu._loaded_models["kokoro"]
    pipe.set_handles(asr=asr_handle, llm=llm_handle, tts=tts_handle)
    return pipe


@pytest.fixture
def silence_1s() -> AudioData:
    """1 second of silence at 16kHz (standard test input)."""
    return AudioData(
        samples=np.zeros(16000, dtype=np.int16),
        sample_rate=16000,
        format=AudioFormat.S16_LE,
    )
