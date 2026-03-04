"""AXCL NPU service — real NPU inference on Raspberry Pi + M5Stack LLM-8850.

Implements the NpuService Protocol using a registry of ModelRunners.
Each model type (LLM, ASR, TTS, VLM) has a dedicated runner:
  - VLM: axllm serve subprocess, OpenAI-compat API (DD-051, Qwen3-VL-2B)
  - LLM: C++ API binary subprocess (DD-046, Qwen3-0.6B/1.7B legacy)
  - ASR: pyaxengine InferenceSession (DD-046)
  - TTS: pyaxengine + onnxruntime (DD-046)

NPU multiplexing confirmed with ~0ms switch overhead (DD-048).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from cortex.hal.npu.runners.asr import ASRRunner
from cortex.hal.npu.runners.llm import LLMRunner
from cortex.hal.npu.runners.tts import TTSRunner
from cortex.hal.npu.runners.vlm import VLMRunner
from cortex.hal.types import (
    InferenceInputs,
    InferenceOutputs,
    ModelHandle,
    NpuCapabilities,
    NpuStatus,
)

logger = logging.getLogger(__name__)

# Model ID → runner type mapping.
# Order matters: _classify_model() uses substring matching and returns
# the first match. "qwen3-vl" must precede "qwen3-" entries because
# "qwen3-vl-2b" contains "qwen3" as a substring.
MODEL_RUNNER_MAP: dict[str, str] = {
    "sensevoice": "asr",
    "qwen3-vl": "vlm",
    "qwen3-1.7b": "llm",
    "qwen3-0.6b": "llm",
    "kokoro": "tts",
    "fastvlm": "vlm",
}


def _classify_model(model_id: str) -> str:
    """Map model_id to runner type via substring matching."""
    model_lower = model_id.lower()
    for key, runner_type in MODEL_RUNNER_MAP.items():
        if key in model_lower:
            return runner_type
    return "unknown"


def _create_runner(runner_type: str) -> LLMRunner | ASRRunner | TTSRunner | VLMRunner:
    """Create a runner instance for the given type."""
    if runner_type == "llm":
        return LLMRunner()
    elif runner_type == "asr":
        return ASRRunner()
    elif runner_type == "tts":
        return TTSRunner()
    elif runner_type == "vlm":
        return VLMRunner()
    else:
        msg = f"Unknown runner type: {runner_type}"
        raise ValueError(msg)


class AxclNpuService:
    """Real NPU service for Raspberry Pi + M5Stack LLM-8850.

    Implements the NpuService Protocol. Manages model lifecycle
    through per-model runners and tracks NPU memory usage.
    """

    def __init__(
        self,
        total_memory_mb: int = 7040,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._total_memory_mb = total_memory_mb
        self._config = config or {}
        self._runners: dict[str, LLMRunner | ASRRunner | TTSRunner | VLMRunner] = {}
        self._handles: dict[str, ModelHandle] = {}

    async def load_model(self, model_id: str, model_path: Path) -> ModelHandle:
        """Load a model onto the NPU.

        Args:
            model_id: Model identifier (e.g., "sensevoice", "qwen3-1.7b")
            model_path: Path to model directory on disk

        Returns:
            ModelHandle for subsequent inference calls

        Raises:
            RuntimeError: On OOM, load failure, or unknown model type
        """
        if model_id in self._runners:
            msg = f"Model {model_id} already loaded"
            raise RuntimeError(msg)

        runner_type = _classify_model(model_id)
        if runner_type == "unknown":
            msg = f"Unknown model type for model_id: {model_id}"
            raise ValueError(msg)

        runner = _create_runner(runner_type)

        # Get model-specific config
        model_config = self._config.get(model_id, {})

        # Check memory before loading
        estimated_mb = model_config.get("memory_mb", 500)
        current_used = sum(r.memory_mb for r in self._runners.values())
        if current_used + estimated_mb > self._total_memory_mb:
            free = self._total_memory_mb - current_used
            msg = f"OOM: {model_id} needs ~{estimated_mb}MB, only {free}MB free"
            raise RuntimeError(msg)

        logger.info("Loading model %s (type=%s, path=%s)", model_id, runner_type, model_path)
        await runner.load(model_path, model_config)

        handle = ModelHandle(
            model_id=model_id,
            _internal={"runner_type": runner_type},
        )
        self._runners[model_id] = runner
        self._handles[model_id] = handle

        logger.info(
            "Model %s loaded (%dMB, total used: %dMB/%dMB)",
            model_id,
            runner.memory_mb,
            sum(r.memory_mb for r in self._runners.values()),
            self._total_memory_mb,
        )
        return handle

    async def unload_model(self, handle: ModelHandle) -> None:
        """Unload a model from the NPU."""
        runner = self._runners.pop(handle.model_id, None)
        self._handles.pop(handle.model_id, None)
        if runner:
            await runner.unload()
            logger.info("Model %s unloaded", handle.model_id)

    async def infer(self, handle: ModelHandle, inputs: InferenceInputs) -> InferenceOutputs:
        """Run inference on a loaded model."""
        runner = self._get_runner(handle)
        return await runner.infer(inputs)

    async def infer_stream(
        self, handle: ModelHandle, inputs: InferenceInputs
    ) -> AsyncIterator[InferenceOutputs]:
        """Stream inference results from a loaded model."""
        runner = self._get_runner(handle)
        async for chunk in runner.infer_stream(inputs):
            yield chunk

    async def get_status(self) -> NpuStatus:
        """Get current NPU status."""
        memory_used = sum(r.memory_mb for r in self._runners.values())

        # TODO: Read actual NPU temperature via AXCL sysfs
        temperature = 0.0

        return NpuStatus(
            temperature_c=temperature,
            memory_used_mb=memory_used,
            memory_total_mb=self._total_memory_mb,
            models_loaded=list(self._runners.keys()),
        )

    @property
    def capabilities(self) -> NpuCapabilities:
        """Static NPU capabilities."""
        return NpuCapabilities(
            total_memory_mb=self._total_memory_mb,
            compute_tops=14.4,
        )

    async def reset_llm_context(self, system_prompt: str | None = None) -> None:
        """Reset LLM/VLM KV cache (convenience method for voice pipeline)."""
        for runner in self._runners.values():
            if isinstance(runner, (LLMRunner, VLMRunner)):
                await runner.reset_context(system_prompt)

    async def shutdown(self) -> None:
        """Unload all models and clean up."""
        for model_id in list(self._runners.keys()):
            handle = self._handles.get(model_id)
            if handle:
                await self.unload_model(handle)
        logger.info("AxclNpuService shut down")

    def _get_runner(self, handle: ModelHandle) -> LLMRunner | ASRRunner | TTSRunner | VLMRunner:
        """Get runner for a handle, raising if not loaded."""
        runner = self._runners.get(handle.model_id)
        if runner is None:
            msg = f"Model {handle.model_id} not loaded"
            raise RuntimeError(msg)
        return runner
