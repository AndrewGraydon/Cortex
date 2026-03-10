"""Tests for Wyoming bridge server."""

from __future__ import annotations

import pytest

from cortex.wyoming.server import MockWyomingBridge, WyomingBridge
from cortex.wyoming.stt_provider import MockAsrBackend, SttProvider
from cortex.wyoming.tts_provider import MockTtsBackend, TtsProvider
from cortex.wyoming.types import BridgeState


@pytest.fixture
def stt_provider() -> SttProvider:
    return SttProvider(backend=MockAsrBackend())


@pytest.fixture
def tts_provider() -> TtsProvider:
    return TtsProvider(backend=MockTtsBackend())


class TestWyomingBridgeInit:
    """Bridge initialization and configuration."""

    def test_default_state_stopped(self, stt_provider: SttProvider) -> None:
        bridge = WyomingBridge(stt_provider=stt_provider)
        assert bridge.state == BridgeState.STOPPED

    def test_stt_only(self, stt_provider: SttProvider) -> None:
        bridge = WyomingBridge(stt_provider=stt_provider)
        assert bridge.stt_enabled is True
        assert bridge.tts_enabled is False

    def test_tts_only(self, tts_provider: TtsProvider) -> None:
        bridge = WyomingBridge(tts_provider=tts_provider)
        assert bridge.stt_enabled is False
        assert bridge.tts_enabled is True

    def test_both_enabled(
        self, stt_provider: SttProvider, tts_provider: TtsProvider
    ) -> None:
        bridge = WyomingBridge(
            stt_provider=stt_provider,
            tts_provider=tts_provider,
        )
        assert bridge.stt_enabled is True
        assert bridge.tts_enabled is True

    def test_neither_enabled(self) -> None:
        bridge = WyomingBridge()
        assert bridge.stt_enabled is False
        assert bridge.tts_enabled is False

    def test_custom_ports(self) -> None:
        bridge = WyomingBridge(stt_port=9001, tts_port=9002)
        assert bridge.stt_port == 9001
        assert bridge.tts_port == 9002

    def test_default_ports(self) -> None:
        bridge = WyomingBridge()
        assert bridge.stt_port == 10300
        assert bridge.tts_port == 10200


class TestWyomingBridgeLifecycle:
    """Bridge start/stop lifecycle."""

    async def test_start_stop(
        self, stt_provider: SttProvider, tts_provider: TtsProvider
    ) -> None:
        bridge = WyomingBridge(
            stt_provider=stt_provider,
            tts_provider=tts_provider,
            host="127.0.0.1",
        )
        await bridge.start()
        assert bridge.state == BridgeState.RUNNING

        await bridge.stop()
        assert bridge.state == BridgeState.STOPPED

    async def test_start_stt_only(self, stt_provider: SttProvider) -> None:
        bridge = WyomingBridge(stt_provider=stt_provider, host="127.0.0.1")
        await bridge.start()
        assert bridge.state == BridgeState.RUNNING
        await bridge.stop()

    async def test_start_tts_only(self, tts_provider: TtsProvider) -> None:
        bridge = WyomingBridge(tts_provider=tts_provider, host="127.0.0.1")
        await bridge.start()
        assert bridge.state == BridgeState.RUNNING
        await bridge.stop()

    async def test_stop_when_stopped_is_noop(self) -> None:
        bridge = WyomingBridge()
        assert bridge.state == BridgeState.STOPPED
        await bridge.stop()  # Should not raise
        assert bridge.state == BridgeState.STOPPED

    async def test_double_start_raises(self, stt_provider: SttProvider) -> None:
        bridge = WyomingBridge(stt_provider=stt_provider, host="127.0.0.1")
        await bridge.start()
        try:
            with pytest.raises(RuntimeError, match="Cannot start bridge"):
                await bridge.start()
        finally:
            await bridge.stop()


class TestWyomingBridgeServiceInfo:
    """Service info aggregation."""

    async def test_stt_info(self, stt_provider: SttProvider) -> None:
        bridge = WyomingBridge(stt_provider=stt_provider)
        info = await bridge.get_service_info()
        assert "asr" in info

    async def test_tts_info(self, tts_provider: TtsProvider) -> None:
        bridge = WyomingBridge(tts_provider=tts_provider)
        info = await bridge.get_service_info()
        assert "tts" in info

    async def test_combined_info(
        self, stt_provider: SttProvider, tts_provider: TtsProvider
    ) -> None:
        bridge = WyomingBridge(
            stt_provider=stt_provider,
            tts_provider=tts_provider,
        )
        info = await bridge.get_service_info()
        assert "asr" in info
        assert "tts" in info

    async def test_empty_info(self) -> None:
        bridge = WyomingBridge()
        info = await bridge.get_service_info()
        assert info == {}


class TestWyomingBridgeHealthCheck:
    """Health check endpoint."""

    async def test_health_check_stopped(self) -> None:
        bridge = WyomingBridge()
        health = await bridge.health_check()
        assert health["state"] == "stopped"

    async def test_health_check_running(self, stt_provider: SttProvider) -> None:
        bridge = WyomingBridge(stt_provider=stt_provider, host="127.0.0.1")
        await bridge.start()
        try:
            health = await bridge.health_check()
            assert health["state"] == "running"
            assert health["stt_enabled"] is True
            assert health["tts_enabled"] is False
            assert health["stt_port"] == 10300
            assert health["tts_port"] is None
        finally:
            await bridge.stop()


class TestMockWyomingBridge:
    """Mock bridge for testing without real TCP."""

    async def test_mock_start_stop(self) -> None:
        bridge = MockWyomingBridge()
        assert bridge.state == BridgeState.STOPPED

        await bridge.start()
        assert bridge.state == BridgeState.RUNNING

        await bridge.stop()
        assert bridge.state == BridgeState.STOPPED

    async def test_mock_with_providers(
        self, stt_provider: SttProvider, tts_provider: TtsProvider
    ) -> None:
        bridge = MockWyomingBridge(
            stt_provider=stt_provider,
            tts_provider=tts_provider,
        )
        assert bridge.stt_enabled is True
        assert bridge.tts_enabled is True
        await bridge.start()
        info = await bridge.get_service_info()
        assert "asr" in info
        assert "tts" in info
        await bridge.stop()

    async def test_mock_health_check(self) -> None:
        bridge = MockWyomingBridge()
        await bridge.start()
        health = await bridge.health_check()
        assert health["state"] == "running"
        await bridge.stop()
