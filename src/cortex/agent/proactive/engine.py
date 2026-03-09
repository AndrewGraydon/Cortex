"""Proactive engine — idle-time think loop for pattern-based suggestions.

Queries the pattern detector, generates candidates, and delivers via
the notification service. Opt-in, disabled by default.
"""

from __future__ import annotations

import logging
import time

from cortex.agent.proactive.detector import PatternDetector
from cortex.agent.proactive.types import ProactiveCandidate, ProactiveType, RoutinePattern

logger = logging.getLogger(__name__)


class ProactiveEngine:
    """Idle-time proactive intelligence engine.

    Args:
        detector: Pattern detector instance.
        enabled: Whether the engine is active.
        think_interval: Seconds between think cycles.
    """

    def __init__(
        self,
        detector: PatternDetector | None = None,
        enabled: bool = False,
        think_interval: float = 300.0,
    ) -> None:
        self._detector = detector or PatternDetector()
        self._enabled = enabled
        self._think_interval = think_interval
        self._last_think: float = 0.0
        self._candidates: list[ProactiveCandidate] = []
        self._delivered: list[ProactiveCandidate] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def think_interval(self) -> float:
        return self._think_interval

    @property
    def candidates(self) -> list[ProactiveCandidate]:
        return list(self._candidates)

    @property
    def delivered(self) -> list[ProactiveCandidate]:
        return list(self._delivered)

    def should_think(self) -> bool:
        """Check if it's time for a think cycle."""
        if not self._enabled:
            return False
        return (time.time() - self._last_think) >= self._think_interval

    def generate_candidates(
        self,
        patterns: list[RoutinePattern],
        current_hour: int,
        current_day: int,
    ) -> list[ProactiveCandidate]:
        """Generate proactive candidates from detected patterns.

        Args:
            patterns: Detected routine patterns.
            current_hour: Current hour (0-23).
            current_day: Current day of week (0=Monday).

        Returns:
            List of proactive candidates for the current time window.
        """
        relevant = self._detector.filter_for_time(patterns, current_hour, current_day)
        candidates: list[ProactiveCandidate] = []

        for pattern in relevant:
            candidate = ProactiveCandidate(
                proactive_type=ProactiveType.ROUTINE_REMINDER,
                title=f"Routine: {pattern.content}",
                message=(
                    f"You usually use '{pattern.content}' around this time "
                    f"({pattern.count} times observed)."
                ),
                priority=3,  # Low priority for routine suggestions
                pattern=pattern,
            )
            candidates.append(candidate)

        self._candidates = candidates
        self._last_think = time.time()
        return candidates

    def mark_delivered(self, candidate: ProactiveCandidate) -> None:
        """Mark a candidate as delivered."""
        self._delivered.append(candidate)
        if candidate in self._candidates:
            self._candidates.remove(candidate)

    def clear(self) -> None:
        """Clear all candidates and delivery history."""
        self._candidates.clear()
        self._delivered.clear()
