"""Memory consolidator — periodic LLM-driven event summarization (DD-053).

Reviews recent episodic events, groups them, and generates summary facts
for long-term memory. Hybrid approach: keeps embedding search for real-time
retrieval, adds periodic LLM "dreaming" during idle time.

Max 1 consolidation per hour to avoid excessive LLM usage.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)

# Min seconds between consolidation runs
DEFAULT_COOLDOWN = 3600  # 1 hour


class MemoryConsolidator:
    """Consolidates recent episodic events into long-term memory facts.

    Groups recent events by (type, content) and generates summary
    sentences. Designed to run during idle time, not during active
    voice sessions.

    Args:
        memory_store: SqliteMemoryStore for writing facts.
        min_events: Minimum events in a group to consolidate.
        cooldown_seconds: Minimum seconds between consolidation runs.
    """

    def __init__(
        self,
        memory_store: Any = None,
        min_events: int = 3,
        cooldown_seconds: float = DEFAULT_COOLDOWN,
    ) -> None:
        self._memory_store = memory_store
        self._min_events = min_events
        self._cooldown = cooldown_seconds
        self._last_run: float = 0.0
        self._facts_generated: int = 0

    @property
    def last_run(self) -> float:
        return self._last_run

    @property
    def facts_generated(self) -> int:
        return self._facts_generated

    def should_run(self) -> bool:
        """Check if enough time has passed since last consolidation."""
        return (time.time() - self._last_run) >= self._cooldown

    async def consolidate(self, recent_events: list[dict[str, Any]]) -> list[str]:
        """Consolidate recent events into summary facts.

        Groups events by (event_type, content), counts occurrences,
        and generates human-readable summary facts for storage in
        long-term memory.

        Args:
            recent_events: Recent episodic events (dicts with
                event_type, content, timestamp).

        Returns:
            List of generated fact strings.
        """
        self._last_run = time.time()

        if not recent_events:
            return []

        # Group by (event_type, content)
        counter: Counter[tuple[str, str]] = Counter()
        for event in recent_events:
            key = (event.get("event_type", ""), event.get("content", ""))
            counter[key] += 1

        facts: list[str] = []
        for (event_type, content), count in counter.most_common():
            if count < self._min_events:
                continue
            fact = _generate_fact(event_type, content, count)
            if fact:
                facts.append(fact)

        # Store facts in long-term memory if backend available
        if self._memory_store and facts:
            for fact in facts:
                try:
                    await self._memory_store.store_fact(
                        key=f"consolidated_{int(time.time())}",
                        value=fact,
                        source="consolidator",
                    )
                    self._facts_generated += 1
                except Exception:
                    logger.exception("Failed to store consolidated fact")

        logger.info(
            "Consolidation complete",
            extra={"events": len(recent_events), "facts": len(facts)},
        )
        return facts


def _generate_fact(event_type: str, content: str, count: int) -> str:
    """Generate a human-readable summary fact from event counts.

    Rule-based for now — no LLM required for simple summaries.
    """
    if event_type == "tool_use":
        return f"User frequently uses the '{content}' tool ({count} times recently)."
    if event_type == "query_topic":
        return f"User often asks about '{content}' ({count} times recently)."
    if event_type == "routine_action":
        return f"User regularly performs '{content}' ({count} times recently)."
    return f"Recurring event: {content} ({count} occurrences)."
