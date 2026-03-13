"""Cortex core service — orchestrates voice pipeline with HAL services.

This is the main application process that:
1. Initializes HAL services (real on Pi, mock fallback on other platforms)
2. Pre-loads NPU models (VLM first to avoid AXCL lifecycle issues)
3. Wires AgentProcessor + ContextAssembler for multi-turn conversations
4. Runs the voice pipeline and web server concurrently
5. Handles graceful shutdown
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from pathlib import Path
from typing import Any

import structlog

from cortex.agent.processor import AgentProcessor
from cortex.agent.router import IntentRouter
from cortex.agent.tools.registry import ToolRegistry
from cortex.config import CortexConfig
from cortex.hal.audio.mock import MockAudioService
from cortex.hal.display.mock import MockButtonService, MockDisplayService
from cortex.hal.npu.mock import MockNpuService
from cortex.hal.types import ModelHandle
from cortex.reasoning.context_assembler import ContextAssembler
from cortex.voice.pipeline import VoicePipeline

logger = structlog.get_logger()

# Default model paths on Pi
DEFAULT_MODELS_DIR = Path.home() / "models"
DEFAULT_SYSTEM_PROMPT = "You are Cortex, a helpful assistant."


class CortexService:
    """Main Cortex service orchestrator.

    In mock mode: uses MockNpuService, MockAudioService, MockDisplayService.
    In real mode: tries real HAL services, falls back to mock per-service.
    """

    def __init__(
        self,
        mock: bool = True,
        models_dir: Path = DEFAULT_MODELS_DIR,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        config: CortexConfig | None = None,
    ) -> None:
        self._mock = mock
        self._models_dir = models_dir
        self._system_prompt = system_prompt
        self._config = config
        self._pipeline: VoicePipeline | None = None
        self._processor: AgentProcessor | None = None
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
            await self._init_real_services()

        # Pre-load models
        await self._load_models()

        # Wire agent framework
        assembler = ContextAssembler()
        self._processor = AgentProcessor(
            router=IntentRouter(),
            registry=ToolRegistry(),
            context_assembler=assembler,
        )
        processor = self._processor

        # Create and configure pipeline
        self._pipeline = VoicePipeline(
            npu=self._npu,
            audio=self._audio,
            display=self._display,
            button=self._button,
            system_prompt=self._system_prompt,
            agent_processor=processor,
            context_assembler=assembler,
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

    async def _init_real_services(self) -> None:
        """Try real HAL services, fall back to mock for each independently.

        Each service is imported and initialized in a separate try/except block.
        The broad exception catch (ImportError, RuntimeError, OSError) handles:
        - ImportError: missing optional dependency (RPi.GPIO, spidev, etc.)
        - RuntimeError: hardware not available (GPIO access, AXCL init failure)
        - OSError: missing system library (PortAudio for sounddevice), device file
        """
        # NPU — AxclNpuService requires AXCL kernel modules (Pi only)
        try:
            from cortex.hal.npu.axcl import AxclNpuService

            # AxclNpuService imports fine on macOS but needs AXCL kernel modules
            if not Path("/dev/axcl_host").exists():
                msg = "AXCL device not found (/dev/axcl_host)"
                raise RuntimeError(msg)  # noqa: TRY301
            self._npu = AxclNpuService()
            logger.info("NPU: using AxclNpuService")
        except (ImportError, RuntimeError, OSError) as exc:
            self._npu = MockNpuService()
            logger.warning("NPU: falling back to mock", reason=str(exc))

        # Audio — AlsaAudioService requires sounddevice + PortAudio
        try:
            from cortex.hal.audio.service import AlsaAudioService

            self._audio = AlsaAudioService()
            logger.info("Audio: using AlsaAudioService")
        except (ImportError, RuntimeError, OSError) as exc:
            self._audio = MockAudioService()
            logger.warning("Audio: falling back to mock", reason=str(exc))

        # Display — WhisplayDisplayService handles its own HW fallback
        try:
            from cortex.hal.display.service import WhisplayDisplayService

            display = WhisplayDisplayService()
            await display.start()
            self._display = display
            logger.info("Display: using WhisplayDisplayService")
        except Exception as exc:
            self._display = MockDisplayService()
            logger.warning("Display: falling back to mock", reason=str(exc))

        # Button — GpioButtonService requires RPi.GPIO (Pi only)
        try:
            from cortex.hal.display.button import GpioButtonService

            button = GpioButtonService()
            await button.start()
            self._button = button
            logger.info("Button: using GpioButtonService")
        except Exception as exc:
            self._button = MockButtonService()
            logger.warning("Button: falling back to mock", reason=str(exc))

    async def run(self) -> None:
        """Run the voice pipeline and web server (blocks until stopped)."""
        if not self._pipeline:
            msg = "Service not started"
            raise RuntimeError(msg)

        logger.info("Cortex voice pipeline running — waiting for button press")

        # Start web server alongside voice pipeline if config is available
        if self._config and self._config.web.enabled:
            web_task = asyncio.create_task(self._run_web_server())
            try:
                await self._pipeline.run()
            finally:
                web_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await web_task
        else:
            await self._pipeline.run()

    async def _run_web_server(self) -> None:
        """Start the FastAPI web server."""
        import uvicorn

        from cortex.web.app import create_app

        web_cfg = self._config.web if self._config else None
        host = web_cfg.host if web_cfg else "0.0.0.0"
        port = web_cfg.port if web_cfg else 8000

        app = create_app(
            config=self._config,
            enable_auth=False,  # Disable auth for local Pi usage
            npu=self._npu,
            llm_handle=self._llm_handle,
            agent_processor=self._processor,
        )

        uvi_config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info",
        )
        server = uvicorn.Server(uvi_config)
        # Prevent uvicorn from overriding our signal handlers (run_cortex handles SIGTERM/SIGINT)
        server.capture_signals = contextlib.nullcontext  # type: ignore[assignment]
        logger.info("Web server starting", host=host, port=port)
        await server.serve()

    async def stop(self) -> None:
        """Graceful shutdown."""
        logger.info("Cortex service stopping")
        self._running = False

        if self._pipeline:
            await self._pipeline.stop()

        # Stop real services that support it
        for service in [self._display, self._button]:
            if service and hasattr(service, "stop"):
                with contextlib.suppress(Exception):
                    await service.stop()

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
        """Pre-load all NPU models.

        VLM loads first: axllm serve subprocess takes ~45s to start and
        should initialize AXCL before pyaxengine models. Repeated axllm
        start/stop cycles can corrupt AXCL kernel module state, so the
        VLM stays loaded for the lifetime of the service.
        """
        logger.info("Loading models...", models_dir=str(self._models_dir))

        asr_path = self._models_dir / "SenseVoice"
        llm_path = self._models_dir / "Qwen3-VL-2B"
        tts_path = self._models_dir / "Kokoro"

        # Validate model directories exist (skip if using MockNpuService)
        if not isinstance(self._npu, MockNpuService):
            missing = [
                (name, path)
                for name, path in [("ASR", asr_path), ("VLM", llm_path), ("TTS", tts_path)]
                if not path.exists()
            ]
            if missing:
                names = ", ".join(f"{name} ({path})" for name, path in missing)
                msg = f"Model directories not found: {names}"
                raise FileNotFoundError(msg)

        # VLM first: slowest to load (~45s), avoids AXCL init conflicts
        self._llm_handle = await self._npu.load_model("qwen3-vl-2b", llm_path)
        logger.info("VLM model loaded", model="qwen3-vl-2b")

        self._asr_handle = await self._npu.load_model("sensevoice", asr_path)
        logger.info("ASR model loaded", model="sensevoice")

        self._tts_handle = await self._npu.load_model("kokoro", tts_path)
        logger.info("TTS model loaded", model="kokoro")

        status = await self._npu.get_status()
        logger.info(
            "All models loaded",
            models=status.models_loaded,
            memory_mb=status.memory_used_mb,
        )


async def run_cortex(
    mock: bool = True,
    models_dir: Path | None = None,
    system_prompt: str | None = None,
    config: CortexConfig | None = None,
) -> None:
    """Main entry point for cortex-core service."""
    kwargs: dict[str, Any] = {"mock": mock}
    if models_dir is not None:
        kwargs["models_dir"] = models_dir
    if system_prompt is not None:
        kwargs["system_prompt"] = system_prompt
    if config is not None:
        kwargs["config"] = config
    service = CortexService(**kwargs)

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
