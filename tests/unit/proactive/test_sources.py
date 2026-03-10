"""Tests for ProactiveDataSources — data aggregation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cortex.agent.proactive.sources import ProactiveDataSources


class TestNoBackends:
    """All sources return empty when no backends configured."""

    @pytest.fixture()
    def sources(self) -> ProactiveDataSources:
        return ProactiveDataSources()

    @pytest.mark.asyncio()
    async def test_no_calendar(self, sources: ProactiveDataSources) -> None:
        assert await sources.get_calendar_events() == []

    @pytest.mark.asyncio()
    async def test_no_weather(self, sources: ProactiveDataSources) -> None:
        assert await sources.get_weather() is None

    @pytest.mark.asyncio()
    async def test_no_reminders(self, sources: ProactiveDataSources) -> None:
        assert await sources.get_active_reminders() == []

    @pytest.mark.asyncio()
    async def test_no_patterns(self, sources: ProactiveDataSources) -> None:
        assert await sources.get_patterns() == []

    @pytest.mark.asyncio()
    async def test_no_iot(self, sources: ProactiveDataSources) -> None:
        assert await sources.get_iot_summary() == {}

    @pytest.mark.asyncio()
    async def test_no_recent_events(self, sources: ProactiveDataSources) -> None:
        assert await sources.get_recent_events() == []


class TestWithMockBackends:
    @pytest.mark.asyncio()
    async def test_scheduling_reminders(self) -> None:
        mock_sched = AsyncMock()
        timer = MagicMock()
        timer.label = "Check oven"
        mock_sched.get_active_timers.return_value = [timer]

        sources = ProactiveDataSources(scheduling_service=mock_sched)
        result = await sources.get_active_reminders()
        assert result == ["Check oven"]

    @pytest.mark.asyncio()
    async def test_iot_summary(self) -> None:
        mock_iot = MagicMock()
        device1 = MagicMock()
        device1.id = "light.1"
        device2 = MagicMock()
        device2.id = "light.2"
        mock_iot.registry.get_all.return_value = [device1, device2]

        state1 = MagicMock()
        state1.is_on = True
        state2 = MagicMock()
        state2.is_on = False
        mock_iot.registry.get_state = lambda did: state1 if did == "light.1" else state2

        sources = ProactiveDataSources(iot_manager=mock_iot)
        result = await sources.get_iot_summary()
        assert result["device_count"] == 2
        assert result["devices_on"] == 1

    @pytest.mark.asyncio()
    async def test_error_handling(self) -> None:
        """Errors in backends return empty, not crash."""
        mock_sched = AsyncMock()
        mock_sched.get_active_timers.side_effect = RuntimeError("DB error")

        sources = ProactiveDataSources(scheduling_service=mock_sched)
        result = await sources.get_active_reminders()
        assert result == []

    @pytest.mark.asyncio()
    async def test_recent_events(self) -> None:
        mock_episodic = AsyncMock()
        event = MagicMock()
        event.event_type.value = "tool_use"
        event.content = "clock"
        event.timestamp = 1000.0
        mock_episodic.query_events.return_value = [event]

        sources = ProactiveDataSources(episodic_store=mock_episodic)
        result = await sources.get_recent_events()
        assert len(result) == 1
        assert result[0]["content"] == "clock"
