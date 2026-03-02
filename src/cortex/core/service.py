"""Cortex core service — orchestrates voice pipeline with HAL services.

This is the main application process that:
1. Connects to HAL services via ZeroMQ
2. Pre-loads NPU models
3. Runs the voice pipeline
4. Handles graceful shutdown
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from pathlib import Path
from typing import Any

import structlog

from cortex.hal.audio.mock import MockAudioService
from cortex.hal.display.mock import MockButtonService, MockDisplayService
from cortex.hal.npu.mock import MockNpuService
from cortex.hal.types import ModelHandle
from cortex.voice.pipeline import VoicePipeline

logger = structlog.get_logger()

# Default model paths on Pi
DEFAULT_MODELS_DIR = Path.home() / "models"
DEFAULT_SYSTEM_PROMPT = (
    "You are Cortex, a helpful voice assistant running locally on a Raspberry Pi. "
    "Be concise and friendly. Keep responses under 50 words when possible."
)


class CortexService:
    """Main Cortex service orchestrator.

    In mock mode: uses MockNpuService, MockAudioService, MockDisplayService.
    In real mode: connects to HAL services via ZeroMQ (Phase 1 uses mock).
    """

    def __init__(
        self,
        mock: bool = True,
        models_dir: Path = DEFAULT_MODELS_DIR,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        self._mock = mock
        self._models_dir = models_dir
        self._system_prompt = system_prompt
        self._pipeline: VoicePipeline | None = None
        self._running = False

        # HAL services
        self._npu: Any = None
        self._audio: Any = None
        self._display: Any = None
        self._button: Any = None

        # Model handles
        self._asr_handle: ModelHandle | None = None
        self._llm_handle: ModelHandle | None = None
        self._tts_handle: ModelHandle | None = None

    async def start(self) -> None:
        """Initialize HAL services, load models, start pipeline."""
        logger.info("Cortex service starting", mock=self._mock)

        # Initialize HAL services
        if self._mock:
            self._npu = MockNpuService()
            self._audio = MockAudioService()
            self._display = MockDisplayService()
            self._button = MockButtonService()
        else:
            # Real mode — import and configure real services
            # For Phase 1, this path is identical to mock
            # Real ZeroMQ IPC integration comes in Phase 1 polish
            self._npu = MockNpuService()
            self._audio = MockAudioService()
            self._display = MockDisplayService()
            self._button = MockButtonService()
            logger.warning("Real HAL not yet wired — using mocks")

        # Pre-load models
        await self._load_models()

        # Create and configure pipeline
        self._pipeline = VoicePipeline(
            npu=self._npu,
            audio=self._audio,
            display=self._display,
            button=self._button,
            system_prompt=self._system_prompt,
        )
        assert self._asr_handle is not None
        assert self._llm_handle is not None
        assert self._tts_handle is not None
        self._pipeline.set_handles(
            asr=self._asr_handle,
            llm=self._llm_handle,
            tts=self._tts_handle,
        )

        self._running = True
        logger.info("Cortex service ready")

    async def run(self) -> None:
        """Run the voice pipeline (blocks until stopped)."""
        if not self._pipeline:
            msg = "Service not started"
            raise RuntimeError(msg)

        logger.info("Cortex voice pipeline running — waiting for button press")
        await self._pipeline.run()

    async def stop(self) -> None:
        """Graceful shutdown."""
        logger.info("Cortex service stopping")
        self._running = False

        if self._pipeline:
            await self._pipeline.stop()

        # Unload models
        if self._npu:
            if hasattr(self._npu, "shutdown"):
                await self._npu.shutdown()
            else:
                for handle in [self._asr_handle, self._llm_handle, self._tts_handle]:
                    if handle:
                        await self._npu.unload_model(handle)

        logger.info("Cortex service stopped")

    async def _load_models(self) -> None:
        """Pre-load all NPU models."""
        logger.info("Loading models...")

        asr_path = self._models_dir / "SenseVoice"
        llm_path = self._models_dir / "Qwen3-1.7B"
        tts_path = self._models_dir / "Kokoro"

        self._asr_handle = await self._npu.load_model("sensevoice", asr_path)
        logger.info("ASR model loaded", model="sensevoice")

        self._llm_handle = await self._npu.load_model("qwen3-1.7b", llm_path)
        logger.info("LLM model loaded", model="qwen3-1.7b")

        self._tts_handle = await self._npu.load_model("kokoro", tts_path)
        logger.info("TTS model loaded", model="kokoro")

        status = await self._npu.get_status()
        logger.info(
            "All models loaded",
            models=status.models_loaded,
            memory_mb=status.memory_used_mb,
        )


async def run_cortex(mock: bool = True) -> None:
    """Main entry point for cortex-core service."""
    service = CortexService(mock=mock)

    stop = asyncio.Event()

    def _signal_handler() -> None:
        stop.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    await service.start()

    # Run pipeline in background, wait for signal
    pipeline_task = asyncio.create_task(service.run())

    await stop.wait()

    await service.stop()
    pipeline_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await pipeline_task
