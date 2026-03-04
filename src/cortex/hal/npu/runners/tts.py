"""TTS runner — wraps Kokoro via pyaxengine + onnxruntime.

Architecture (DD-046):
  Uses Kokoro Python class from model directory.
  3 axmodel parts on NPU (via axengine) + 1 ONNX vocoder on CPU.
  Fixed 96-phoneme sequence length, auto-splits longer text.

Input: text string + voice name + language
Output: float32 audio numpy array at 24kHz
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

DEFAULT_VOICE = "af_heart"
DEFAULT_LANGUAGE = "en"
DEFAULT_SAMPLE_RATE = 24000


class TTSRunner:
    """Kokoro TTS via pyaxengine + onnxruntime.

    Loads the Kokoro Python module from the model directory.
    Uses NPU for model parts 1-3 and CPU for the harmonic generator (ONNX).
    """

    def __init__(self) -> None:
        self._model: Any = None
        self._loaded = False
        self._memory_mb = 0
        self._model_path: Path | None = None
        self._default_voice: str = DEFAULT_VOICE
        self._voices_dir: Path | None = None

    @property
    def model_type(self) -> str:
        return "tts"

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def memory_mb(self) -> int:
        return self._memory_mb

    async def load(self, model_path: Path, config: dict[str, Any]) -> None:
        """Load Kokoro TTS model.

        Args:
            model_path: Path to Kokoro model directory (e.g., ~/models/Kokoro)
            config: Configuration dict with optional overrides:
                - memory_mb: NPU memory in MB (default 232)
                - default_voice: Default voice name (default "af_heart")
                - max_seq_len: Max phoneme sequence length (default 96)
        """
        if self._loaded:
            msg = "TTS already loaded"
            raise RuntimeError(msg)

        self._model_path = model_path
        self._memory_mb = config.get("memory_mb", 232)
        self._default_voice = config.get("default_voice", DEFAULT_VOICE)

        # Load in thread pool (Kokoro init is slow, ~9s)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_sync, model_path, config)

        self._loaded = True
        logger.info("TTS loaded: Kokoro from %s", model_path)

    def _load_sync(self, model_path: Path, config: dict[str, Any]) -> None:
        """Synchronous model loading (runs in thread pool)."""
        # Add model directory to path for imports
        path_str = str(model_path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)

        # Apply compat patches for axengine 0.1.3 lifecycle bugs
        try:
            from cortex.hal.npu._axengine_compat import patch as _patch_axengine

            _patch_axengine()
        except ImportError:
            pass

        # Import Kokoro
        mod = importlib.import_module("kokoro_ax")
        kokoro_cls = mod.Kokoro

        max_seq_len = config.get("max_seq_len", 96)

        # Find model subdirectory (axmodel files)
        axmodel_dir = model_path / "models"
        if not axmodel_dir.exists():
            msg = f"Kokoro models directory not found: {axmodel_dir}"
            raise FileNotFoundError(msg)

        # Find config
        config_path = model_path / "checkpoints" / "config.json"
        if not config_path.exists():
            msg = f"Kokoro config not found: {config_path}"
            raise FileNotFoundError(msg)

        # Locate voices directory
        self._voices_dir = model_path / "checkpoints" / "voices_npy"
        if not self._voices_dir.exists():
            msg = f"Kokoro voices directory not found: {self._voices_dir}"
            raise FileNotFoundError(msg)

        self._model = kokoro_cls(
            axmodel_dir=str(axmodel_dir),
            config_path=str(config_path),
            max_seq_len=max_seq_len,
        )

    async def unload(self) -> None:
        """Unload model and free resources."""
        self._model = None
        self._loaded = False
        self._memory_mb = 0
        self._voices_dir = None
        logger.info("TTS unloaded")

    async def infer(self, inputs: InferenceInputs) -> InferenceOutputs:
        """Synthesize text to audio.

        Args:
            inputs: InferenceInputs where:
                - data: text string to synthesize
                - params.voice: Voice name (default "af_heart")
                - params.language: Language ("en", "zh", "ja")
                - params.speed: Speech speed multiplier (default 1.0)

        Returns:
            InferenceOutputs with data=float32 numpy array at 24kHz
        """
        self._check_loaded()

        text = str(inputs.data) if inputs.data else ""
        if not text.strip():
            # Return empty audio for empty text
            return InferenceOutputs(
                data=np.zeros(0, dtype=np.float32),
                metadata={"sample_rate": DEFAULT_SAMPLE_RATE, "duration_s": 0.0},
            )

        voice = inputs.params.get("voice", self._default_voice)
        language = inputs.params.get("language", DEFAULT_LANGUAGE)
        speed = inputs.params.get("speed", 1.0)

        # Resolve voice file path
        voice_path = self._resolve_voice(voice)

        # Run inference in thread pool (Kokoro is synchronous)
        loop = asyncio.get_event_loop()
        audio = await loop.run_in_executor(
            None, self._infer_sync, text, language, voice_path, speed
        )

        duration_s = len(audio) / DEFAULT_SAMPLE_RATE if len(audio) > 0 else 0.0

        return InferenceOutputs(
            data=audio,
            metadata={
                "sample_rate": DEFAULT_SAMPLE_RATE,
                "duration_s": duration_s,
            },
        )

    async def infer_stream(self, inputs: InferenceInputs) -> AsyncIterator[InferenceOutputs]:
        """TTS is non-streaming at model level — yields single result."""
        yield await self.infer(inputs)

    def _infer_sync(self, text: str, language: str, voice_path: str, speed: float) -> np.ndarray:
        """Synchronous inference (runs in thread pool)."""
        audio: np.ndarray = self._model.run(
            text=text,
            language=language,
            voice=voice_path,
            sample_rate=DEFAULT_SAMPLE_RATE,
            speed=speed,
        )
        return audio

    def _resolve_voice(self, voice: str) -> str:
        """Resolve voice name to .npy file path."""
        assert self._voices_dir is not None

        # If already a path, use directly
        if voice.endswith(".npy"):
            return voice

        voice_file = self._voices_dir / f"{voice}.npy"
        if not voice_file.exists():
            logger.warning("Voice '%s' not found, using default '%s'", voice, self._default_voice)
            voice_file = self._voices_dir / f"{self._default_voice}.npy"

        return str(voice_file)

    def _check_loaded(self) -> None:
        if not self._loaded:
            msg = "TTS not loaded"
            raise RuntimeError(msg)
