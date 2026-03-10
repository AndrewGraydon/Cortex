"""Briefing builder — composes morning briefings from multiple sources.

Combines calendar events, reminders, detected patterns, weather,
and smart home state into a formatted briefing for TTS or display.
"""

from __future__ import annotations

import logging
from typing import Any

from cortex.agent.proactive.types import ProactiveCandidate, ProactiveType, RoutinePattern

logger = logging.getLogger(__name__)


class BriefingBuilder:
    """Builds morning briefings from available data sources."""

    def build(
        self,
        calendar_events: list[dict[str, Any]] | None = None,
        reminders: list[str] | None = None,
        patterns: list[RoutinePattern] | None = None,
        weather: dict[str, Any] | None = None,
        iot_summary: dict[str, Any] | None = None,
    ) -> ProactiveCandidate:
        """Build a morning briefing from available data.

        Args:
            calendar_events: Today's calendar events (dicts with summary, start_time).
            reminders: Active reminders/timers.
            patterns: Detected routine patterns for today.
            weather: Weather data (dict with 'display' key for formatted text).
            iot_summary: Smart home summary (dict with device_count, devices_on).

        Returns:
            ProactiveCandidate with formatted briefing.
        """
        sections: list[str] = []

        # Weather section (first, most relevant for morning)
        if weather:
            display = weather.get("display", "")
            if display:
                sections.append(f"Weather: {display}")

        # Calendar section
        if calendar_events:
            cal_lines = [f"- {e.get('summary', 'Event')}" for e in calendar_events]
            sections.append("Today's events:\n" + "\n".join(cal_lines))
        else:
            sections.append("No calendar events today.")

        # Reminders section
        if reminders:
            rem_lines = [f"- {r}" for r in reminders]
            sections.append("Reminders:\n" + "\n".join(rem_lines))

        # Smart home section
        if iot_summary and iot_summary.get("device_count", 0) > 0:
            on = iot_summary.get("devices_on", 0)
            total = iot_summary["device_count"]
            sections.append(f"Smart home: {on} of {total} devices on.")

        # Patterns section
        if patterns:
            pat_lines = [f"- {p.content} (usual at {p.hour}:00)" for p in patterns[:3]]
            sections.append("Your routines:\n" + "\n".join(pat_lines))

        message = "\n\n".join(sections) if sections else "Good morning! Nothing scheduled today."

        return ProactiveCandidate(
            proactive_type=ProactiveType.MORNING_BRIEFING,
            title="Morning Briefing",
            message=message,
            priority=2,
        )
