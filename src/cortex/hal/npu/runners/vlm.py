"""VLM runner — stub for Phase 1.

FastVLM-0.5B uses pyaxengine via InferManager (DD-046).
Full implementation deferred to Phase 2.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from cortex.hal.types import InferenceInputs, InferenceOutputs

logger = logging.getLogger(__name__)


class VLMRunner:
    """FastVLM-0.5B stub — not implemented in Phase 1."""

    def __init__(self) -> None:
        self._loaded = False

    @property
    def model_type(self) -> str:
        return "vlm"

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def memory_mb(self) -> int:
        return 792 if self._loaded else 0

    async def load(self, model_path: Path, config: dict[str, Any]) -> None:
        logger.warning("VLM runner is a Phase 1 stub — not loading real model")
        self._loaded = True

    async def unload(self) -> None:
        self._loaded = False

    async def infer(self, inputs: InferenceInputs) -> InferenceOutputs:
        msg = "VLM inference not implemented in Phase 1"
        raise NotImplementedError(msg)

    async def infer_stream(self, inputs: InferenceInputs) -> AsyncIterator[InferenceOutputs]:
        msg = "VLM inference not implemented in Phase 1"
        raise NotImplementedError(msg)
        yield  # pragma: no cover — make this a generator
