"""Tests for MockNpuService — realistic mock NPU for off-Pi development."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cortex.hal.npu.mock import MockError, MockNpuService
from cortex.hal.types import InferenceInputs


@pytest.fixture
def mock_npu() -> MockNpuService:
    return MockNpuService()


class TestModelLifecycle:
    async def test_load_model(self, mock_npu: MockNpuService) -> None:
        handle = await mock_npu.load_model("sensevoice", Path("/models/sensevoice"))
        assert handle.model_id == "sensevoice"
        status = await mock_npu.get_status()
        assert "sensevoice" in status.models_loaded
        assert status.memory_used_mb == 251

    async def test_load_multiple_models(self, mock_npu: MockNpuService) -> None:
        await mock_npu.load_model("sensevoice", Path("/models/sensevoice"))
        await mock_npu.load_model("qwen3-1.7b", Path("/models/qwen3"))
        await mock_npu.load_model("kokoro", Path("/models/kokoro"))
        status = await mock_npu.get_status()
        assert len(status.models_loaded) == 3
        assert status.memory_used_mb == 251 + 3375 + 232

    async def test_unload_model(self, mock_npu: MockNpuService) -> None:
        handle = await mock_npu.load_model("sensevoice", Path("/models/sensevoice"))
        await mock_npu.unload_model(handle)
        status = await mock_npu.get_status()
        assert "sensevoice" not in status.models_loaded
        assert status.memory_used_mb == 0

    async def test_oom_on_overload(self, mock_npu: MockNpuService) -> None:
        """Cannot load models exceeding total NPU memory."""
        mock_npu.total_memory_mb = 4000
        await mock_npu.load_model("qwen3-1.7b", Path("/models/qwen3"))  # 3375MB
        with pytest.raises(RuntimeError, match="OOM"):
            await mock_npu.load_model("qwen3-0.6b", Path("/models/qwen06"))  # 2011MB > remaining


class TestASRInference:
    async def test_asr_returns_text(self, mock_npu: MockNpuService) -> None:
        handle = await mock_npu.load_model("sensevoice", Path("/models/sensevoice"))
        audio = np.zeros(16000, dtype=np.int16)
        inputs = InferenceInputs(data=audio, params={"mock_text": "Turn on the lights"})
        result = await mock_npu.infer(handle, inputs)
        assert result.data == "Turn on the lights"
        assert result.metadata["confidence"] == 0.95

    async def test_asr_default_text(self, mock_npu: MockNpuService) -> None:
        handle = await mock_npu.load_model("sensevoice", Path("/models/sensevoice"))
        inputs = InferenceInputs(data=np.zeros(16000, dtype=np.int16))
        result = await mock_npu.infer(handle, inputs)
        assert isinstance(result.data, str)
        assert len(result.data) > 0


class TestLLMInference:
    async def test_llm_full_response(self, mock_npu: MockNpuService) -> None:
        handle = await mock_npu.load_model("qwen3-1.7b", Path("/models/qwen3"))
        inputs = InferenceInputs(data="What can you do?")
        result = await mock_npu.infer(handle, inputs)
        assert isinstance(result.data, str)
        assert len(result.data) > 0
        assert result.metadata["finish_reason"] == "stop"

    async def test_llm_streaming(self, mock_npu: MockNpuService) -> None:
        handle = await mock_npu.load_model("qwen3-1.7b", Path("/models/qwen3"))
        inputs = InferenceInputs(data="Hello")

        chunks: list[str] = []
        async for output in mock_npu.infer_stream(handle, inputs):
            chunks.append(str(output.data))

        assert len(chunks) > 1
        full_text = "".join(chunks)
        assert len(full_text) > 0
        # Last chunk should be final
        # (checked via metadata in the stream)

    async def test_llm_cycles_responses(self, mock_npu: MockNpuService) -> None:
        handle = await mock_npu.load_model("qwen3-1.7b", Path("/models/qwen3"))
        inputs = InferenceInputs(data="test")
        r1 = await mock_npu.infer(handle, inputs)
        r2 = await mock_npu.infer(handle, inputs)
        # Should cycle through different responses
        assert r1.data != r2.data


class TestTTSInference:
    async def test_tts_returns_audio(self, mock_npu: MockNpuService) -> None:
        handle = await mock_npu.load_model("kokoro", Path("/models/kokoro"))
        inputs = InferenceInputs(data="Hello world, this is a test.")
        result = await mock_npu.infer(handle, inputs)
        assert isinstance(result.data, np.ndarray)
        assert result.data.dtype == np.float32
        assert result.metadata["sample_rate"] == 24000
        assert result.metadata["duration_s"] > 0


class TestErrorInjection:
    async def test_load_failure(self, mock_npu: MockNpuService) -> None:
        mock_npu.inject_error(
            MockError(model_id="sensevoice", error_type="load_failure", message="NPU init failed")
        )
        with pytest.raises(RuntimeError, match="NPU init failed"):
            await mock_npu.load_model("sensevoice", Path("/models/sensevoice"))

    async def test_inference_error(self, mock_npu: MockNpuService) -> None:
        handle = await mock_npu.load_model("qwen3-1.7b", Path("/models/qwen3"))
        mock_npu.inject_error(
            MockError(
                model_id="qwen3-1.7b", error_type="inference_error", message="Inference timeout"
            )
        )
        with pytest.raises(RuntimeError, match="Inference timeout"):
            await mock_npu.infer(handle, InferenceInputs(data="test"))

    async def test_error_consumed_after_trigger(self, mock_npu: MockNpuService) -> None:
        """Injected errors are one-shot — trigger once then gone."""
        mock_npu.inject_error(
            MockError(model_id="sensevoice", error_type="load_failure", message="Fail once")
        )
        with pytest.raises(RuntimeError):
            await mock_npu.load_model("sensevoice", Path("/models/sensevoice"))

        # Second attempt should succeed
        handle = await mock_npu.load_model("sensevoice", Path("/models/sensevoice"))
        assert handle.model_id == "sensevoice"

    async def test_clear_errors(self, mock_npu: MockNpuService) -> None:
        mock_npu.inject_error(MockError(model_id="sensevoice", error_type="load_failure"))
        mock_npu.clear_errors()
        handle = await mock_npu.load_model("sensevoice", Path("/models/sensevoice"))
        assert handle.model_id == "sensevoice"


class TestUnloadedModelRejection:
    async def test_infer_unloaded_model(self, mock_npu: MockNpuService) -> None:
        handle = await mock_npu.load_model("sensevoice", Path("/m"))
        await mock_npu.unload_model(handle)
        with pytest.raises(RuntimeError, match="not loaded"):
            await mock_npu.infer(handle, InferenceInputs(data="test"))

    async def test_stream_unloaded_model(self, mock_npu: MockNpuService) -> None:
        handle = await mock_npu.load_model("qwen3-1.7b", Path("/m"))
        await mock_npu.unload_model(handle)
        with pytest.raises(RuntimeError, match="not loaded"):
            async for _ in mock_npu.infer_stream(handle, InferenceInputs(data="test")):
                pass


class TestCapabilities:
    def test_capabilities(self, mock_npu: MockNpuService) -> None:
        caps = mock_npu.capabilities
        assert caps.total_memory_mb == 7040
        assert caps.compute_tops == 14.4
        assert "axmodel" in caps.supported_formats


class TestFullPipelineCycle:
    async def test_asr_llm_tts_cycle(self, mock_npu: MockNpuService) -> None:
        """Full voice pipeline mock: ASR → LLM → TTS."""
        # Load all models
        asr_handle = await mock_npu.load_model("sensevoice", Path("/m"))
        llm_handle = await mock_npu.load_model("qwen3-1.7b", Path("/m"))
        tts_handle = await mock_npu.load_model("kokoro", Path("/m"))

        # ASR
        audio_in = np.zeros(16000, dtype=np.int16)
        asr_result = await mock_npu.infer(
            asr_handle, InferenceInputs(data=audio_in, params={"mock_text": "What time is it?"})
        )
        assert asr_result.data == "What time is it?"

        # LLM (streaming)
        llm_text_parts: list[str] = []
        async for chunk in mock_npu.infer_stream(
            llm_handle, InferenceInputs(data=str(asr_result.data))
        ):
            llm_text_parts.append(str(chunk.data))
        llm_text = "".join(llm_text_parts)
        assert len(llm_text) > 0

        # TTS
        tts_result = await mock_npu.infer(tts_handle, InferenceInputs(data=llm_text))
        assert isinstance(tts_result.data, np.ndarray)
        assert tts_result.data.dtype == np.float32
        assert tts_result.metadata["sample_rate"] == 24000

        # Verify memory
        status = await mock_npu.get_status()
        assert status.memory_used_mb == 251 + 3375 + 232
