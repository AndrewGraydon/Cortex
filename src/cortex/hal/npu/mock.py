"""Mock NPU service for off-Pi development and testing.

Simulates realistic timing based on Phase 0 measured benchmarks:
- SenseVoice ASR: RTF 0.028 (36x real-time)
- Qwen3-1.7B LLM: 7.70 tok/s, prefill ~1.0s
- Kokoro TTS: RTF 0.115, 9s init
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from cortex.hal.types import (
    InferenceInputs,
    InferenceOutputs,
    ModelHandle,
    NpuCapabilities,
    NpuStatus,
)

# --- Mock timing constants (from Phase 0 measured benchmarks) ---

MOCK_ASR_LATENCY_S = 0.05  # ~50ms for short utterances (RTF 0.028)
MOCK_LLM_PREFILL_S = 1.0  # ~1s prefill for short prompt
MOCK_LLM_TOKENS_PER_S = 7.70  # measured decode speed
MOCK_TTS_RTF = 0.115  # measured Python path RTF
MOCK_TTS_SAMPLE_RATE = 24000

# Canned responses for mock LLM
MOCK_LLM_RESPONSES = [
    "I'm Cortex, your local voice assistant running on a Raspberry Pi. How can I help you today?",
    "The weather looks nice outside. Would you like me to check the forecast?",
    "I can help with that. Let me think about it for a moment.",
    "That's an interesting question. Here's what I know about it.",
]


@dataclass
class MockError:
    """Configurable error injection for testing."""

    model_id: str
    error_type: str  # "load_failure", "timeout", "oom", "inference_error"
    message: str = "Mock error"


@dataclass
class MockNpuService:
    """Realistic mock NPU for off-Pi development.

    Implements the NpuService Protocol with simulated timing.
    Supports configurable error injection for testing error paths.
    """

    total_memory_mb: int = 7040
    _loaded_models: dict[str, ModelHandle] = field(default_factory=dict)
    _errors: list[MockError] = field(default_factory=list)
    _response_index: int = 0
    _memory_used_mb: int = 0
    _asr_text: str | None = None

    # Model memory sizes (from Phase 0 measurements)
    _model_sizes: dict[str, int] = field(
        default_factory=lambda: {
            "sensevoice": 251,
            "qwen3-1.7b": 3375,
            "qwen3-0.6b": 2011,
            "kokoro": 232,
            "fastvlm-0.5b": 792,
        }
    )

    def set_asr_text(self, text: str) -> None:
        """Set the text that mock ASR will return on next inference."""
        self._asr_text = text

    def inject_error(self, error: MockError) -> None:
        """Add an error to be triggered on next matching operation."""
        self._errors.append(error)

    def clear_errors(self) -> None:
        """Remove all injected errors."""
        self._errors.clear()

    def _check_error(self, model_id: str, error_type: str) -> None:
        for i, err in enumerate(self._errors):
            if err.model_id == model_id and err.error_type == error_type:
                self._errors.pop(i)
                raise RuntimeError(err.message)

    async def load_model(self, model_id: str, model_path: Path) -> ModelHandle:
        self._check_error(model_id, "load_failure")

        size = self._model_sizes.get(model_id, 500)
        if self._memory_used_mb + size > self.total_memory_mb:
            free = self.total_memory_mb - self._memory_used_mb
            msg = f"OOM: {model_id} needs {size}MB, only {free}MB free"
            raise RuntimeError(msg)

        # Simulate load time (~100ms per model)
        await asyncio.sleep(0.1)

        handle = ModelHandle(model_id=model_id, _internal={"mock": True})
        self._loaded_models[model_id] = handle
        self._memory_used_mb += size
        return handle

    async def unload_model(self, handle: ModelHandle) -> None:
        if handle.model_id in self._loaded_models:
            size = self._model_sizes.get(handle.model_id, 500)
            self._memory_used_mb = max(0, self._memory_used_mb - size)
            del self._loaded_models[handle.model_id]

    async def infer(self, handle: ModelHandle, inputs: InferenceInputs) -> InferenceOutputs:
        self._check_error(handle.model_id, "inference_error")

        if handle.model_id not in self._loaded_models:
            msg = f"Model {handle.model_id} not loaded"
            raise RuntimeError(msg)

        model_type = self._classify_model(handle.model_id)

        if model_type == "asr":
            return await self._mock_asr(inputs)
        elif model_type == "tts":
            return await self._mock_tts(inputs)
        elif model_type == "llm":
            return await self._mock_llm_full(inputs)
        else:
            return InferenceOutputs(data="mock output", metadata={"model": handle.model_id})

    async def infer_stream(
        self, handle: ModelHandle, inputs: InferenceInputs
    ) -> AsyncIterator[InferenceOutputs]:
        self._check_error(handle.model_id, "inference_error")

        if handle.model_id not in self._loaded_models:
            msg = f"Model {handle.model_id} not loaded"
            raise RuntimeError(msg)

        model_type = self._classify_model(handle.model_id)

        if model_type == "llm":
            async for chunk in self._mock_llm_stream(inputs):
                yield chunk
        else:
            yield await self.infer(handle, inputs)

    async def get_status(self) -> NpuStatus:
        return NpuStatus(
            temperature_c=55.0,
            memory_used_mb=self._memory_used_mb,
            memory_total_mb=self.total_memory_mb,
            models_loaded=list(self._loaded_models.keys()),
        )

    @property
    def capabilities(self) -> NpuCapabilities:
        return NpuCapabilities(
            total_memory_mb=self.total_memory_mb,
            compute_tops=14.4,
        )

    # --- Internal mock implementations ---

    def _classify_model(self, model_id: str) -> str:
        if "sensevoice" in model_id:
            return "asr"
        elif "kokoro" in model_id:
            return "tts"
        elif "qwen" in model_id:
            return "llm"
        elif "vlm" in model_id or "vl" in model_id:
            return "vlm"
        return "unknown"

    async def _mock_asr(self, inputs: InferenceInputs) -> InferenceOutputs:
        """Mock ASR — returns canned text after realistic delay."""
        await asyncio.sleep(MOCK_ASR_LATENCY_S)
        text = self._asr_text or inputs.params.get("mock_text", "Hello, how are you?")
        return InferenceOutputs(
            data=text,
            metadata={
                "language": "en",
                "confidence": 0.95,
                "duration_ms": MOCK_ASR_LATENCY_S * 1000,
            },
        )

    async def _mock_llm_full(self, inputs: InferenceInputs) -> InferenceOutputs:
        """Mock LLM — returns full response after realistic delay."""
        response = self._next_response()
        token_count = len(response.split())
        total_time = MOCK_LLM_PREFILL_S + token_count / MOCK_LLM_TOKENS_PER_S
        await asyncio.sleep(total_time)
        return InferenceOutputs(
            data=response,
            metadata={"tokens": token_count, "finish_reason": "stop"},
        )

    async def _mock_llm_stream(self, inputs: InferenceInputs) -> AsyncIterator[InferenceOutputs]:
        """Mock LLM streaming — yields tokens at measured decode speed."""
        response = self._next_response()
        words = response.split()

        # Simulate prefill
        await asyncio.sleep(MOCK_LLM_PREFILL_S)

        inter_token_delay = 1.0 / MOCK_LLM_TOKENS_PER_S
        for i, word in enumerate(words):
            await asyncio.sleep(inter_token_delay)
            is_final = i == len(words) - 1
            text = word if i == 0 else " " + word
            yield InferenceOutputs(
                data=text,
                metadata={
                    "token_count": 1,
                    "is_final": is_final,
                    "finish_reason": "stop" if is_final else None,
                },
            )

    async def _mock_tts(self, inputs: InferenceInputs) -> InferenceOutputs:
        """Mock TTS — returns silence audio at realistic timing."""
        text = str(inputs.data) if inputs.data else ""
        # Estimate audio duration: ~150ms per word
        word_count = max(1, len(text.split()))
        audio_duration_s = word_count * 0.15
        synthesis_time = audio_duration_s * MOCK_TTS_RTF
        await asyncio.sleep(synthesis_time)

        num_samples = int(audio_duration_s * MOCK_TTS_SAMPLE_RATE)
        silence = np.zeros(num_samples, dtype=np.float32)
        return InferenceOutputs(
            data=silence,
            metadata={
                "sample_rate": MOCK_TTS_SAMPLE_RATE,
                "duration_s": audio_duration_s,
                "rtf": MOCK_TTS_RTF,
            },
        )

    def _next_response(self) -> str:
        response = MOCK_LLM_RESPONSES[self._response_index % len(MOCK_LLM_RESPONSES)]
        self._response_index += 1
        return response
