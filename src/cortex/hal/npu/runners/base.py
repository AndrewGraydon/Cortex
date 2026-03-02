"""Base protocol for NPU model runners."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from cortex.hal.types import InferenceInputs, InferenceOutputs


@runtime_checkable
class ModelRunner(Protocol):
    """Per-model inference runner.

    Each model type (LLM, ASR, TTS, VLM) has a runner that handles
    loading, unloading, and inference for that specific model.
    """

    @property
    def model_type(self) -> str:
        """Model type identifier (e.g., 'llm', 'asr', 'tts', 'vlm')."""
        ...

    @property
    def is_loaded(self) -> bool:
        """Whether the model is currently loaded."""
        ...

    @property
    def memory_mb(self) -> int:
        """Estimated NPU memory usage in MB."""
        ...

    async def load(self, model_path: Path, config: dict[str, Any]) -> None:
        """Load the model. Raises RuntimeError on failure."""
        ...

    async def unload(self) -> None:
        """Unload the model and free resources."""
        ...

    async def infer(self, inputs: InferenceInputs) -> InferenceOutputs:
        """Run inference. Raises RuntimeError if not loaded."""
        ...

    async def infer_stream(self, inputs: InferenceInputs) -> AsyncIterator[InferenceOutputs]:
        """Stream inference results. Default: yields single full result."""
        ...
