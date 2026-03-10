"""Tests for CortexService — mock mode and real-service fallback."""

from __future__ import annotations

import pytest

from cortex.core.service import CortexService


class TestMockMode:
    """CortexService in mock mode uses all mock services."""

    async def test_start_creates_pipeline(self) -> None:
        service = CortexService(mock=True)
        await service.start()
        assert service._pipeline is not None
        await service.stop()

    async def test_mock_mode_loads_models(self) -> None:
        service = CortexService(mock=True)
        await service.start()
        assert service._asr_handle is not None
        assert service._llm_handle is not None
        assert service._tts_handle is not None
        await service.stop()

    async def test_pipeline_has_agent_processor(self) -> None:
        service = CortexService(mock=True)
        await service.start()
        assert service._pipeline._agent_processor is not None
        await service.stop()

    async def test_pipeline_has_context_assembler(self) -> None:
        service = CortexService(mock=True)
        await service.start()
        assert service._pipeline._context_assembler is not None
        await service.stop()

    async def test_stop_without_start(self) -> None:
        service = CortexService(mock=True)
        # Should not raise
        await service.stop()

    async def test_run_without_start_raises(self) -> None:
        service = CortexService(mock=True)
        with pytest.raises(RuntimeError, match="Service not started"):
            await service.run()


class TestRealModeFallback:
    """On macOS/non-Pi, real mode falls back to mocks for each service."""

    async def test_real_mode_falls_back_gracefully(self) -> None:
        service = CortexService(mock=False)
        await service.start()
        # On macOS, all services should have fallen back to mocks
        # but the pipeline should still be functional
        assert service._pipeline is not None
        assert service._asr_handle is not None
        await service.stop()

    async def test_real_mode_has_agent_processor(self) -> None:
        service = CortexService(mock=False)
        await service.start()
        assert service._pipeline._agent_processor is not None
        await service.stop()
