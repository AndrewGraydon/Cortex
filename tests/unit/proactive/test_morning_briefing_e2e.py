"""End-to-end test: morning briefing pipeline.

Tests the full path: scheduler fires → sources aggregate → builder formats
→ engine delivers via notification service.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cortex.agent.notifications import Notification, NotificationService
from cortex.agent.proactive.briefing import BriefingBuilder
from cortex.agent.proactive.engine import ProactiveEngine
from cortex.agent.proactive.sources import ProactiveDataSources
from cortex.agent.proactive.types import ProactiveType, RoutinePattern


class TestBriefingWithWeather:
    def test_weather_section_included(self) -> None:
        builder = BriefingBuilder()
        candidate = builder.build(
            weather={"display": "Currently 18°C and partly cloudy."},
        )
        assert "18°C" in candidate.message
        assert "Weather:" in candidate.message

    def test_iot_summary_included(self) -> None:
        builder = BriefingBuilder()
        candidate = builder.build(
            iot_summary={"device_count": 5, "devices_on": 2},
        )
        assert "2 of 5" in candidate.message
        assert "Smart home:" in candidate.message

    def test_full_briefing(self) -> None:
        builder = BriefingBuilder()
        candidate = builder.build(
            calendar_events=[{"summary": "Team standup"}],
            reminders=["Buy groceries"],
            patterns=[RoutinePattern("tool_use", "clock", 8, 0, 10)],
            weather={"display": "Sunny, 22°C."},
            iot_summary={"device_count": 3, "devices_on": 1},
        )
        assert candidate.proactive_type == ProactiveType.MORNING_BRIEFING
        assert candidate.priority == 2
        assert "Sunny" in candidate.message
        assert "Team standup" in candidate.message
        assert "Buy groceries" in candidate.message
        assert "clock" in candidate.message
        assert "1 of 3" in candidate.message

    def test_empty_iot_summary_not_shown(self) -> None:
        builder = BriefingBuilder()
        candidate = builder.build(
            iot_summary={"device_count": 0, "devices_on": 0},
        )
        assert "Smart home:" not in candidate.message


class TestEngineDeliverCandidate:
    @pytest.mark.asyncio()
    async def test_deliver_to_notification_service(self) -> None:
        delivered: list[Notification] = []

        async def on_deliver(n: Notification) -> None:
            delivered.append(n)

        notif_service = NotificationService()
        notif_service.set_on_deliver(on_deliver)

        engine = ProactiveEngine(
            notification_service=notif_service,
        )
        builder = BriefingBuilder()
        candidate = builder.build(
            weather={"display": "Rainy, 12°C."},
        )
        result = await engine.deliver_candidate(candidate)
        assert result is True
        assert len(delivered) == 1
        assert delivered[0].source == "proactive"
        assert "Rainy" in delivered[0].body

    @pytest.mark.asyncio()
    async def test_deliver_without_notification_service(self) -> None:
        engine = ProactiveEngine()
        builder = BriefingBuilder()
        candidate = builder.build()
        result = await engine.deliver_candidate(candidate)
        assert result is False
        assert len(engine.delivered) == 1


class TestEngineThinkCycle:
    @pytest.mark.asyncio()
    async def test_think_cycle_with_sources(self) -> None:
        mock_episodic = AsyncMock()
        mock_episodic.get_routine_patterns.return_value = []
        mock_episodic.query_events.return_value = []

        sources = ProactiveDataSources(episodic_store=mock_episodic)

        delivered: list[Notification] = []

        async def on_deliver(n: Notification) -> None:
            delivered.append(n)

        notif_service = NotificationService()
        notif_service.set_on_deliver(on_deliver)

        engine = ProactiveEngine(
            enabled=True,
            notification_service=notif_service,
            sources=sources,
        )
        await engine._run_think_cycle()
        # No patterns → no candidates
        assert len(delivered) == 0

    @pytest.mark.asyncio()
    async def test_handle_event_triggers(self) -> None:
        from cortex.agent.proactive.triggers import EventTrigger

        engine = ProactiveEngine(enabled=True)
        engine.triggers.register(EventTrigger(
            trigger_id="temp_high",
            name="High Temperature",
            event_type="iot_state",
            condition=lambda d: d.get("temperature", 0) > 30,
            cooldown_seconds=0.0,
        ))

        candidates = engine.handle_event("iot_state", {"temperature": 35})
        assert len(candidates) == 1
        assert "High Temperature" in candidates[0].title

    @pytest.mark.asyncio()
    async def test_morning_briefing_delivery(self) -> None:
        """Full morning briefing: sources → builder → deliver."""
        mock_sched = AsyncMock()
        timer = MagicMock()
        timer.label = "Dentist appointment"
        mock_sched.get_active_timers.return_value = [timer]

        sources = ProactiveDataSources(scheduling_service=mock_sched)

        delivered: list[Notification] = []

        async def on_deliver(n: Notification) -> None:
            delivered.append(n)

        notif_service = NotificationService()
        notif_service.set_on_deliver(on_deliver)

        engine = ProactiveEngine(
            enabled=True,
            notification_service=notif_service,
            sources=sources,
        )
        await engine._deliver_morning_briefing()

        assert len(delivered) == 1
        assert "Morning Briefing" in delivered[0].title
        assert "Dentist appointment" in delivered[0].body

    @pytest.mark.asyncio()
    async def test_session_awareness(self) -> None:
        engine = ProactiveEngine(enabled=True)
        assert engine.in_session is False
        engine.in_session = True
        assert engine.in_session is True


class TestEngineStartStop:
    @pytest.mark.asyncio()
    async def test_start_stop(self) -> None:
        engine = ProactiveEngine(enabled=False)
        await engine.start()
        assert engine._running is True
        await engine.stop()
        assert engine._running is False

    @pytest.mark.asyncio()
    async def test_start_with_briefing(self) -> None:
        engine = ProactiveEngine(enabled=False)
        await engine.start(
            morning_briefing_enabled=True,
            morning_briefing_hour=8,
            morning_briefing_minute=30,
        )
        schedules = engine.scheduler.schedules
        assert any(s.schedule_id == "morning_briefing" for s in schedules)
        await engine.stop()

    @pytest.mark.asyncio()
    async def test_start_with_consolidation(self) -> None:
        engine = ProactiveEngine(enabled=False)
        await engine.start(
            consolidation_enabled=True,
            consolidation_interval_minutes=30,
        )
        schedules = engine.scheduler.schedules
        assert any(s.schedule_id == "memory_consolidation" for s in schedules)
        await engine.stop()
