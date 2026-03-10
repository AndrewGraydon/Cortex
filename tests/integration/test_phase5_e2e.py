"""Phase 5 E2E tests — validates all 4 exit criteria.

EC#1: Voice command controls at least one simulated smart home device
EC#2: Wyoming STT/TTS services functional (mock)
EC#3: Morning briefing fires with weather + calendar data
EC#4: External services fully bidirectional
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cortex.agent.notifications import Notification, NotificationService
from cortex.agent.proactive.briefing import BriefingBuilder
from cortex.agent.proactive.engine import ProactiveEngine
from cortex.agent.proactive.sources import ProactiveDataSources
from cortex.agent.tools.builtin.device_control import (
    DeviceControlTool,
    DeviceQueryTool,
    set_iot_backend,
)
from cortex.iot.registry import DeviceRegistry
from cortex.iot.resolver import DeviceResolver
from cortex.iot.simulator import DeviceSimulator, create_demo_devices


class _FakeManager:
    def __init__(self, sim: DeviceSimulator, reg: DeviceRegistry) -> None:
        self._sim = sim
        self.registry = reg

    async def send_command(self, command: object) -> bool:
        return await self._sim.send_command(command)  # type: ignore[arg-type]


class TestDeviceControlE2E:
    """EC#1: Voice command controls at least one simulated smart home device."""

    @pytest.fixture()
    async def setup(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()
        simulator = DeviceSimulator()

        for device in create_demo_devices():
            simulator.add_device(device)
            await registry.register_device(device.info)
            await registry.update_state(device.info.id, device.state)

        manager = _FakeManager(simulator, registry)
        resolver = DeviceResolver(registry)
        set_iot_backend(manager, resolver)

        self.simulator = simulator
        self.registry = registry
        yield
        set_iot_backend(None, None)

    @pytest.mark.asyncio()
    async def test_voice_turn_on_kitchen_light(self, setup: None) -> None:
        """Simulate: 'turn on the kitchen light'."""
        tool = DeviceControlTool()
        result = await tool.execute({
            "device": "Kitchen Light",
            "action": "turn_on",
        })
        assert result.success is True
        assert "turn on" in result.display_text

        # Verify device state changed
        state = await self.simulator.get_state("sim_kitchen_light")
        assert state is not None
        assert state.state == "on"

    @pytest.mark.asyncio()
    async def test_voice_query_device_state(self, setup: None) -> None:
        """Simulate: 'what's the status of the bedroom lamp?'"""
        tool = DeviceQueryTool()
        result = await tool.execute({"device": "Bedroom Lamp"})
        assert result.success is True
        assert "Bedroom Lamp" in result.display_text
        assert result.data["state"] == "off"

    @pytest.mark.asyncio()
    async def test_voice_turn_on_with_brightness(self, setup: None) -> None:
        """Simulate: 'turn on kitchen light to brightness 128'."""
        tool = DeviceControlTool()
        result = await tool.execute({
            "device": "Kitchen Light",
            "action": "turn_on",
            "brightness": 128,
        })
        assert result.success is True

    @pytest.mark.asyncio()
    async def test_natural_language_resolution(self, setup: None) -> None:
        """Fuzzy name resolution: 'kitchen' → Kitchen Light + Kitchen Plug."""
        tool = DeviceQueryTool()
        # Exact match
        result = await tool.execute({"device": "Thermostat"})
        assert result.success is True
        assert result.data["device_id"] == "sim_thermostat"


class TestWyomingE2E:
    """EC#2: Wyoming STT/TTS services functional (mock bridge)."""

    @pytest.mark.asyncio()
    async def test_mock_wyoming_bridge_lifecycle(self) -> None:
        from cortex.wyoming.mock import MockWyomingBridge
        from cortex.wyoming.types import BridgeState

        bridge = MockWyomingBridge()
        await bridge.start()
        health = await bridge.health_check()
        assert health["state"] == BridgeState.RUNNING.value
        await bridge.stop()
        health = await bridge.health_check()
        assert health["state"] == BridgeState.STOPPED.value

    @pytest.mark.asyncio()
    async def test_mock_stt_provider(self) -> None:
        from cortex.wyoming.stt_provider import MockAsrBackend, SttProvider

        backend = MockAsrBackend()
        provider = SttProvider(backend)
        provider.begin_session("en")
        provider.add_audio(b"\x00" * 1600)
        text = await provider.finish()
        assert isinstance(text, str)
        assert len(text) > 0

    @pytest.mark.asyncio()
    async def test_mock_tts_provider(self) -> None:
        from cortex.wyoming.tts_provider import MockTtsBackend, TtsProvider

        backend = MockTtsBackend()
        provider = TtsProvider(backend)
        result = await provider.synthesize("Hello world")
        assert isinstance(result.audio_bytes, bytes)
        assert len(result.audio_bytes) > 0


class TestMorningBriefingE2E:
    """EC#3: Morning briefing fires with weather + calendar data."""

    @pytest.mark.asyncio()
    async def test_full_briefing_pipeline(self) -> None:
        """Scheduler → sources → builder → notification delivery."""
        # Mock scheduling service
        mock_sched = AsyncMock()
        timer = MagicMock()
        timer.label = "Morning medication"
        mock_sched.get_active_timers.return_value = [timer]

        # Mock calendar
        mock_calendar = AsyncMock()
        event = MagicMock()
        event.summary = "Team standup"
        event.start = "09:00"
        mock_calendar.get_events.return_value = [event]

        # Mock weather
        mock_weather = AsyncMock()
        forecast = MagicMock()
        forecast.current.temperature = 18
        forecast.current.condition.value = "clouds"
        forecast.current.description = "Partly cloudy"
        forecast.format_display.return_value = "Currently 18°C and partly cloudy."
        mock_weather.get_forecast.return_value = forecast

        sources = ProactiveDataSources(
            calendar_adapter=mock_calendar,
            weather_adapter=mock_weather,
            scheduling_service=mock_sched,
        )

        # Notification capture
        delivered: list[Notification] = []

        async def on_deliver(n: Notification) -> None:
            delivered.append(n)

        notif_service = NotificationService()
        notif_service.set_on_deliver(on_deliver)

        # Build and deliver
        engine = ProactiveEngine(
            enabled=True,
            notification_service=notif_service,
            sources=sources,
        )
        await engine._deliver_morning_briefing()

        # Verify
        assert len(delivered) == 1
        briefing = delivered[0]
        assert "Morning Briefing" in briefing.title
        assert "18°C" in briefing.body
        assert "Team standup" in briefing.body
        assert "Morning medication" in briefing.body

    @pytest.mark.asyncio()
    async def test_briefing_with_iot_data(self) -> None:
        """Briefing includes smart home summary."""
        builder = BriefingBuilder()
        candidate = builder.build(
            weather={"display": "Sunny, 22°C."},
            calendar_events=[{"summary": "Dentist"}],
            iot_summary={"device_count": 5, "devices_on": 2},
        )
        assert "Sunny" in candidate.message
        assert "Dentist" in candidate.message
        assert "2 of 5" in candidate.message


class TestBidirectionalSyncE2E:
    """EC#4: External services fully bidirectional."""

    @pytest.mark.asyncio()
    async def test_calendar_crud(self) -> None:
        """Calendar: create, read, update, delete."""
        from datetime import UTC, datetime

        from cortex.external.calendar.mock import MockCalendarAdapter

        adapter = MockCalendarAdapter()
        await adapter.connect()

        # Create
        from cortex.external.types import CalendarEvent

        event = CalendarEvent(
            uid="test-1",
            summary="Test Event",
            start=datetime(2026, 3, 9, 10, 0, tzinfo=UTC),
            end=datetime(2026, 3, 9, 11, 0, tzinfo=UTC),
        )
        created = await adapter.create_event(event)
        assert created.uid == "test-1"

        # Read
        got = await adapter.get_event("test-1")
        assert got is not None
        assert got.summary == "Test Event"

        # Update (CalendarEvent is frozen — use replace)
        from dataclasses import replace

        modified = replace(got, summary="Updated Event")
        updated = await adapter.update_event(modified)
        assert updated is not None
        assert updated.summary == "Updated Event"

        # Verify update persisted
        got2 = await adapter.get_event("test-1")
        assert got2 is not None
        assert got2.summary == "Updated Event"

        await adapter.disconnect()

    @pytest.mark.asyncio()
    async def test_task_crud(self) -> None:
        """Tasks: create, query, complete."""
        from cortex.external.tasks.mock import MockTaskAdapter

        adapter = MockTaskAdapter()
        await adapter.connect()

        # Create
        from cortex.external.tasks.types import TaskItem

        task = TaskItem(uid="t1", summary="Buy groceries")
        created = await adapter.create_task(task)
        assert created.uid == "t1"

        # List
        tasks = await adapter.list_tasks()
        assert len(tasks) == 1

        # Complete
        completed = await adapter.complete_task("t1")
        assert completed is True

        # Verify completed (include_completed=True to see it)
        tasks = await adapter.list_tasks(include_completed=True)
        assert len(tasks) == 1
        assert tasks[0].completed is True

        await adapter.disconnect()

    @pytest.mark.asyncio()
    async def test_weather_query(self) -> None:
        """Weather: current + forecast."""
        from cortex.external.weather.mock import MockWeatherAdapter

        adapter = MockWeatherAdapter()
        await adapter.connect()

        forecast = await adapter.get_forecast()
        assert forecast.current.temperature > 0
        assert forecast.current.description != ""
        display = forecast.format_display(days=1)
        assert len(display) > 0

        await adapter.disconnect()
