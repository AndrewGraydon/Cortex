"""Proactive data sources — aggregates data for briefings and triggers.

Collects calendar events, weather, reminders, patterns, and IoT state.
Each method returns data or empty list if the backend is unavailable.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from cortex.agent.proactive.types import RoutinePattern

logger = logging.getLogger(__name__)


class ProactiveDataSources:
    """Aggregates data from external services for proactive features.

    Each source is optional — methods return empty/None if backend
    is not configured. Designed for the morning briefing and think loop.
    """

    def __init__(
        self,
        calendar_adapter: Any = None,
        weather_adapter: Any = None,
        scheduling_service: Any = None,
        episodic_store: Any = None,
        iot_manager: Any = None,
    ) -> None:
        self._calendar = calendar_adapter
        self._weather = weather_adapter
        self._scheduling = scheduling_service
        self._episodic = episodic_store
        self._iot = iot_manager

    async def get_calendar_events(self) -> list[dict[str, Any]]:
        """Get today's calendar events."""
        if self._calendar is None:
            return []
        try:
            from datetime import datetime, timedelta

            today = datetime.now()  # noqa: DTZ005
            tomorrow = today + timedelta(days=1)
            events = await self._calendar.get_events(
                start=today.replace(hour=0, minute=0, second=0),
                end=tomorrow.replace(hour=0, minute=0, second=0),
            )
            return [
                {"summary": e.summary, "start_time": str(e.start)}
                for e in events
            ]
        except Exception:
            logger.exception("Failed to fetch calendar events")
            return []

    async def get_weather(self) -> dict[str, Any] | None:
        """Get current weather data."""
        if self._weather is None:
            return None
        try:
            forecast = await self._weather.get_forecast()
            return {
                "current": {
                    "temperature": forecast.current.temperature,
                    "condition": forecast.current.condition.value,
                    "description": forecast.current.description,
                },
                "display": forecast.format_display(days=1),
            }
        except Exception:
            logger.exception("Failed to fetch weather")
            return None

    async def get_active_reminders(self) -> list[str]:
        """Get active timer/reminder labels."""
        if self._scheduling is None:
            return []
        try:
            timers = await self._scheduling.get_active_timers()
            return [t.label for t in timers]
        except Exception:
            logger.exception("Failed to fetch reminders")
            return []

    async def get_patterns(
        self, min_occurrences: int = 5, days_back: int = 30,
    ) -> list[RoutinePattern]:
        """Get detected routine patterns from episodic memory."""
        if self._episodic is None:
            return []
        try:
            from cortex.agent.proactive.detector import PatternDetector

            raw = await self._episodic.get_routine_patterns(min_occurrences, days_back)
            detector = PatternDetector(min_occurrences, days_back)
            return detector.detect_patterns(raw)
        except Exception:
            logger.exception("Failed to detect patterns")
            return []

    async def get_iot_summary(self) -> dict[str, Any]:
        """Get smart home device summary."""
        if self._iot is None:
            return {}
        try:
            devices = self._iot.registry.get_all()
            on_count = sum(
                1 for d in devices
                if (s := self._iot.registry.get_state(d.id)) and s.is_on
            )
            return {
                "device_count": len(devices),
                "devices_on": on_count,
            }
        except Exception:
            logger.exception("Failed to get IoT summary")
            return {}

    async def get_recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent episodic events for consolidation."""
        if self._episodic is None:
            return []
        try:
            since = time.time() - 86400  # last 24h
            events = await self._episodic.query_events(since=since, limit=limit)
            return [
                {
                    "event_type": e.event_type.value,
                    "content": e.content,
                    "timestamp": e.timestamp,
                }
                for e in events
            ]
        except Exception:
            logger.exception("Failed to fetch recent events")
            return []
