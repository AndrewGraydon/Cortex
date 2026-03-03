"""ASR runner — wraps SenseVoice via pyaxengine.

Architecture (DD-046):
  Uses SenseVoiceAx Python class from model directory,
  which calls axengine.InferenceSession for NPU inference.
  Single axmodel, one-shot (non-autoregressive) inference.

Input: numpy float32 audio array (16kHz mono)
Output: transcribed text string
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import numpy as np

from cortex.hal.types import InferenceInputs, InferenceOutputs

logger = logging.getLogger(__name__)


class ASRRunner:
    """SenseVoice ASR via pyaxengine.

    Loads the SenseVoice Python module from the model directory
    and uses it for speech-to-text inference on the NPU.
    """

    def __init__(self) -> None:
        self._model: Any = None
        self._loaded = False
        self._memory_mb = 0
        self._model_path: Path | None = None

    @property
    def model_type(self) -> str:
        return "asr"

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def memory_mb(self) -> int:
        return self._memory_mb

    async def load(self, model_path: Path, config: dict[str, Any]) -> None:
        """Load SenseVoice model.

        Args:
            model_path: Path to SenseVoice model directory
                        (e.g., ~/models/SenseVoice)
            config: Configuration dict with optional overrides:
                - memory_mb: NPU memory in MB (default 251)
                - max_seq_len: Max sequence length (default 256)
                - language: Default language (default "auto")
        """
        if self._loaded:
            msg = "ASR already loaded"
            raise RuntimeError(msg)

        self._model_path = model_path
        self._memory_mb = config.get("memory_mb", 251)

        # Load in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_sync, model_path, config)

        self._loaded = True
        logger.info("ASR loaded: SenseVoice from %s", model_path)

    def _load_sync(self, model_path: Path, config: dict[str, Any]) -> None:
        """Synchronous model loading (runs in thread pool)."""
        python_dir = model_path / "python"
        if not python_dir.exists():
            msg = f"SenseVoice python directory not found: {python_dir}"
            raise FileNotFoundError(msg)

        # Add model's Python directory to path for imports
        path_str = str(python_dir)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)

        # Import SenseVoiceAx
        mod = importlib.import_module("SenseVoiceAx")
        sensevoice_cls = mod.SenseVoiceAx

        # Find model files
        axmodel_dir = model_path / "sensevoice_ax650"
        if not axmodel_dir.exists():
            # Try alternative directory names
            for candidate in model_path.iterdir():
                if candidate.is_dir() and "sensevoice" in candidate.name.lower():
                    axmodel_dir = candidate
                    break

        max_seq_len = config.get("max_seq_len", 256)

        # Detect available axengine provider
        try:
            import axengine as axe

            providers = axe.get_available_providers()
            logger.info("Available axengine providers: %s", providers)
        except ImportError:
            providers = ["AXCLRTExecutionProvider"]

        self._model = sensevoice_cls(
            model_path=str(axmodel_dir / "sensevoice.axmodel"),
            cmvn_file=str(axmodel_dir / "am.mvn"),
            token_file=str(axmodel_dir / "tokens.txt"),
            bpe_model=str(axmodel_dir / "chn_jpn_yue_eng_ko_spectok.bpe.model"),
            max_seq_len=max_seq_len,
            streaming=False,
            providers=providers,
        )

    async def unload(self) -> None:
        """Unload model and free resources."""
        self._model = None
        self._loaded = False
        self._memory_mb = 0
        logger.info("ASR unloaded")

    async def infer(self, inputs: InferenceInputs) -> InferenceOutputs:
        """Transcribe audio to text.

        Args:
            inputs: InferenceInputs where:
                - data: numpy array (int16 or float32) of audio at 16kHz
                - params.language: Language hint ("auto", "en", "zh", etc.)
                - params.sample_rate: Sample rate if not 16kHz

        Returns:
            InferenceOutputs with data=transcribed text string
        """
        self._check_loaded()

        audio = inputs.data
        language = inputs.params.get("language", "auto")
        sample_rate = inputs.params.get("sample_rate", 16000)

        # Convert int16 to float32 normalized
        if isinstance(audio, np.ndarray) and audio.dtype == np.int16:
            audio = audio.astype(np.float32) / 32768.0

        # Run inference in thread pool (SenseVoice is synchronous)
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, self._infer_sync, audio, sample_rate, language)

        return InferenceOutputs(
            data=text,
            metadata={
                "language": language,
            },
        )

    async def infer_stream(self, inputs: InferenceInputs) -> AsyncIterator[InferenceOutputs]:
        """ASR is non-streaming — yields single result."""
        yield await self.infer(inputs)

    def _infer_sync(self, audio: Any, sample_rate: int, language: str) -> str:
        """Synchronous inference (runs in thread pool)."""
        # SenseVoice accepts (waveform, sample_rate) tuple or file path
        result = self._model.infer((audio, sample_rate), language=language)
        return str(result) if result else ""

    def _check_loaded(self) -> None:
        if not self._loaded:
            msg = "ASR not loaded"
            raise RuntimeError(msg)
