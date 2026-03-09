"""Briefing builder — composes morning briefings from multiple sources.

Combines calendar events, reminders, and detected patterns into
a formatted briefing text for delivery via TTS or display.
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
    ) -> ProactiveCandidate:
        """Build a morning briefing from available data.

        Args:
            calendar_events: Today's calendar events (dicts with summary, start_time).
            reminders: Active reminders/timers.
            patterns: Detected routine patterns for today.

        Returns:
            ProactiveCandidate with formatted briefing.
        """
        sections: list[str] = []

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
