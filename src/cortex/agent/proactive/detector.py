"""Pattern detector — queries episodic memory for routine patterns.

Pure rule-based detection: groups events by (type, hour, day_of_week),
identifies routines with >= min_occurrences. No LLM required.
"""

from __future__ import annotations

import logging
from typing import Any

from cortex.agent.proactive.types import RoutinePattern

logger = logging.getLogger(__name__)


class PatternDetector:
    """Detects routine patterns from episodic memory data.

    Args:
        min_occurrences: Minimum occurrences for a pattern to be detected.
        days_back: Number of days of history to analyze.
    """

    def __init__(
        self,
        min_occurrences: int = 5,
        days_back: int = 30,
    ) -> None:
        self._min_occurrences = min_occurrences
        self._days_back = days_back

    @property
    def min_occurrences(self) -> int:
        return self._min_occurrences

    @property
    def days_back(self) -> int:
        return self._days_back

    def detect_patterns(self, raw_patterns: list[dict[str, Any]]) -> list[RoutinePattern]:
        """Detect routine patterns from raw episodic data.

        Args:
            raw_patterns: Output from EpisodicMemoryStore.get_routine_patterns().
                Each dict has: event_type, content, hour, day_of_week, count.

        Returns:
            List of RoutinePattern objects, sorted by count descending.
        """
        patterns: list[RoutinePattern] = []

        for raw in raw_patterns:
            count = raw.get("count", 0)
            if count < self._min_occurrences:
                continue

            # Simple confidence: count / expected_max (cap at 1.0)
            expected_max = self._days_back  # rough: max 1 per day
            confidence = min(count / max(expected_max, 1), 1.0)

            patterns.append(
                RoutinePattern(
                    event_type=raw["event_type"],
                    content=raw["content"],
                    hour=raw["hour"],
                    day_of_week=raw["day_of_week"],
                    count=count,
                    confidence=confidence,
                )
            )

        # Sort by count descending
        patterns.sort(key=lambda p: p.count, reverse=True)
        return patterns

    def filter_for_time(
        self,
        patterns: list[RoutinePattern],
        current_hour: int,
        current_day: int,
    ) -> list[RoutinePattern]:
        """Filter patterns that match the current time window.

        Returns patterns matching current hour (+/- 1) and day of week.
        """
        return [
            p for p in patterns if p.day_of_week == current_day and abs(p.hour - current_hour) <= 1
        ]
