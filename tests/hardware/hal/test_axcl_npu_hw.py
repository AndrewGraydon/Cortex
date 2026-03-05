"""Hardware tests for AxclNpuService — requires Pi + NPU.

Run with: make test-hw
Or: pytest -m hardware tests/hardware/

Note: The axengine NPU engine (axclrtEngineInit) is process-global and can only
be initialized once. The npu fixture is module-scoped so all tests share one
AxclNpuService instance, avoiding re-initialization failures.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from cortex.hal.npu.axcl import AxclNpuService
from cortex.hal.types import InferenceInputs

# Standard model paths on Pi
MODELS_DIR = Path.home() / "models"
SENSEVOICE_DIR = MODELS_DIR / "SenseVoice"
QWEN3_VL_DIR = MODELS_DIR / "Qwen3-VL-2B"
KOKORO_DIR = MODELS_DIR / "Kokoro"

pytestmark = pytest.mark.hardware


@pytest.fixture(scope="module")
async def npu() -> AsyncGenerator[AxclNpuService, Any]:
    """Module-scoped NPU service — avoids axclrtEngineInit re-initialization.

    All tests share one AxclNpuService instance. Models are cleaned up
    between tests by the _cleanup_models autouse fixture.
    """
    service = AxclNpuService(
        config={
            "sensevoice": {"memory_mb": 251},
            "qwen3-vl-2b": {
                "memory_mb": 1771,
                "system_prompt": "You are Cortex, a helpful voice assistant.",
            },
            "kokoro": {"memory_mb": 232, "default_voice": "af_heart"},
        }
    )
    yield service
    await service.shutdown()


@pytest.fixture(autouse=True)
async def _cleanup_models(npu: AxclNpuService) -> AsyncGenerator[None, Any]:
    """Unload all models after each test to avoid state leaking between tests."""
    yield
    # Unload any models left loaded by the test
    for model_id in list(npu._runners.keys()):
        handle = npu._handles.get(model_id)
        if handle:
            await npu.unload_model(handle)


class TestASRHardware:
    async def test_sensevoice_load_and_infer(self, npu: AxclNpuService) -> None:
        """Load SenseVoice and transcribe silence (should return empty/short text)."""
        if not SENSEVOICE_DIR.exists():
            pytest.skip("SenseVoice model not found")

        handle = await npu.load_model("sensevoice", SENSEVOICE_DIR)
        assert handle.model_id == "sensevoice"

        # Feed 1 second of silence at 16kHz
        silence = np.zeros(16000, dtype=np.int16)
        result = await npu.infer(handle, InferenceInputs(data=silence))
        assert isinstance(result.data, str)

    async def test_sensevoice_memory_tracking(self, npu: AxclNpuService) -> None:
        if not SENSEVOICE_DIR.exists():
            pytest.skip("SenseVoice model not found")

        handle = await npu.load_model("sensevoice", SENSEVOICE_DIR)
        status = await npu.get_status()
        assert "sensevoice" in status.models_loaded
        assert status.memory_used_mb >= 200

        await npu.unload_model(handle)
        status = await npu.get_status()
        assert "sensevoice" not in status.models_loaded


class TestVLMHardware:
    async def test_qwen3_vl_load_and_infer(self, npu: AxclNpuService) -> None:
        """Load Qwen3-VL-2B and generate a text response."""
        if not QWEN3_VL_DIR.exists():
            pytest.skip("Qwen3-VL-2B model not found")

        handle = await npu.load_model("qwen3-vl-2b", QWEN3_VL_DIR)
        assert handle.model_id == "qwen3-vl-2b"

        result = await npu.infer(handle, InferenceInputs(data="What is 2+2?"))
        assert isinstance(result.data, str)
        assert len(result.data) > 0
        assert result.metadata.get("finish_reason") == "stop"

    async def test_qwen3_vl_streaming(self, npu: AxclNpuService) -> None:
        """Stream tokens from Qwen3-VL-2B."""
        if not QWEN3_VL_DIR.exists():
            pytest.skip("Qwen3-VL-2B model not found")

        handle = await npu.load_model("qwen3-vl-2b", QWEN3_VL_DIR)
        chunks: list[str] = []
        async for output in npu.infer_stream(handle, InferenceInputs(data="Say hello")):
            chunks.append(str(output.data))

        assert len(chunks) > 0
        full_text = "".join(chunks)
        assert len(full_text) > 0

    async def test_qwen3_vl_think_tag_stripping(self, npu: AxclNpuService) -> None:
        """Verify think tags are stripped from Qwen3-VL-2B output."""
        if not QWEN3_VL_DIR.exists():
            pytest.skip("Qwen3-VL-2B model not found")

        handle = await npu.load_model("qwen3-vl-2b", QWEN3_VL_DIR)
        result = await npu.infer(handle, InferenceInputs(data="What is 2+2? Be brief."))
        # Output should not contain think tags (VLMRunner strips them)
        assert "<think>" not in str(result.data)
        assert "</think>" not in str(result.data)


class TestTTSHardware:
    async def test_kokoro_load_and_infer(self, npu: AxclNpuService) -> None:
        """Load Kokoro and synthesize audio."""
        if not KOKORO_DIR.exists():
            pytest.skip("Kokoro model not found")

        handle = await npu.load_model("kokoro", KOKORO_DIR)
        assert handle.model_id == "kokoro"

        result = await npu.infer(
            handle,
            InferenceInputs(data="Hello world, this is a test."),
        )
        assert isinstance(result.data, np.ndarray)
        assert result.data.dtype == np.float32
        assert result.metadata["sample_rate"] == 24000
        assert result.metadata["duration_s"] > 0


class TestMultiModelHardware:
    async def test_asr_tts_co_resident(self, npu: AxclNpuService) -> None:
        """Load ASR + TTS simultaneously and interleave inference (DD-048)."""
        if not SENSEVOICE_DIR.exists() or not KOKORO_DIR.exists():
            pytest.skip("SenseVoice or Kokoro model not found")

        asr_handle = await npu.load_model("sensevoice", SENSEVOICE_DIR)
        tts_handle = await npu.load_model("kokoro", KOKORO_DIR)

        # ASR
        silence = np.zeros(16000, dtype=np.int16)
        asr_result = await npu.infer(asr_handle, InferenceInputs(data=silence))
        assert isinstance(asr_result.data, str)

        # TTS
        tts_result = await npu.infer(
            tts_handle,
            InferenceInputs(data="Test multiplexing."),
        )
        assert isinstance(tts_result.data, np.ndarray)

        status = await npu.get_status()
        assert len(status.models_loaded) == 2

    async def test_full_pipeline_cycle(self, npu: AxclNpuService) -> None:
        """Full ASR → VLM → TTS cycle on real hardware."""
        for d in [SENSEVOICE_DIR, QWEN3_VL_DIR, KOKORO_DIR]:
            if not d.exists():
                pytest.skip(f"Model not found: {d}")

        asr_handle = await npu.load_model("sensevoice", SENSEVOICE_DIR)
        llm_handle = await npu.load_model("qwen3-vl-2b", QWEN3_VL_DIR)
        tts_handle = await npu.load_model("kokoro", KOKORO_DIR)

        # ASR: transcribe silence (will get empty/short text)
        audio_in = np.zeros(16000, dtype=np.int16)
        await npu.infer(asr_handle, InferenceInputs(data=audio_in))

        # LLM: generate response
        llm_result = await npu.infer(llm_handle, InferenceInputs(data="Say hello in one sentence."))
        assert len(str(llm_result.data)) > 0

        # TTS: synthesize
        tts_result = await npu.infer(tts_handle, InferenceInputs(data=str(llm_result.data)))
        assert isinstance(tts_result.data, np.ndarray)
        assert tts_result.metadata["sample_rate"] == 24000

        # Verify all three models loaded
        status = await npu.get_status()
        assert len(status.models_loaded) == 3
