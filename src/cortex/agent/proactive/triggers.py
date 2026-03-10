"""Event trigger system — callbacks for IoT state changes, timers, calendar.

Generates ProactiveCandidates from real-time events. Triggers are
registered by the ProactiveEngine and fire asynchronously.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from cortex.agent.proactive.types import ProactiveCandidate, ProactiveType

logger = logging.getLogger(__name__)


@dataclass
class EventTrigger:
    """A registered trigger that watches for specific events."""

    trigger_id: str
    name: str
    event_type: str  # "iot_state", "timer_fire", "calendar_approaching"
    condition: Callable[[dict[str, Any]], bool] | None = None
    candidate_builder: Callable[[dict[str, Any]], ProactiveCandidate] | None = None
    enabled: bool = True
    fire_count: int = 0
    last_fired: float = 0.0
    cooldown_seconds: float = 300.0  # Min seconds between firings


@dataclass
class TriggerResult:
    """Result of evaluating triggers against an event."""

    candidates: list[ProactiveCandidate] = field(default_factory=list)
    triggers_fired: int = 0


class TriggerManager:
    """Manages event triggers and evaluates them against incoming events."""

    def __init__(self) -> None:
        self._triggers: dict[str, EventTrigger] = {}

    @property
    def triggers(self) -> list[EventTrigger]:
        return list(self._triggers.values())

    def register(self, trigger: EventTrigger) -> None:
        """Register an event trigger."""
        self._triggers[trigger.trigger_id] = trigger

    def unregister(self, trigger_id: str) -> None:
        """Remove a trigger."""
        self._triggers.pop(trigger_id, None)

    def evaluate(self, event_type: str, event_data: dict[str, Any]) -> TriggerResult:
        """Evaluate all matching triggers against an event.

        Args:
            event_type: Type of event (e.g., "iot_state", "timer_fire").
            event_data: Event payload.

        Returns:
            TriggerResult with generated candidates.
        """
        result = TriggerResult()
        now = time.time()

        for trigger in self._triggers.values():
            if not trigger.enabled:
                continue
            if trigger.event_type != event_type:
                continue

            # Check cooldown
            if trigger.last_fired and (now - trigger.last_fired) < trigger.cooldown_seconds:
                continue

            # Check condition
            if trigger.condition and not trigger.condition(event_data):
                continue

            # Build candidate
            candidate = _build_candidate(trigger, event_data)
            result.candidates.append(candidate)
            trigger.fire_count += 1
            trigger.last_fired = now
            result.triggers_fired += 1

        return result

    def clear(self) -> None:
        """Remove all triggers."""
        self._triggers.clear()


def _build_candidate(
    trigger: EventTrigger, event_data: dict[str, Any],
) -> ProactiveCandidate:
    """Build a ProactiveCandidate from a trigger firing."""
    if trigger.candidate_builder:
        return trigger.candidate_builder(event_data)

    # Default candidate
    return ProactiveCandidate(
        proactive_type=ProactiveType.IOT_ALERT,
        title=trigger.name,
        message=f"Event trigger '{trigger.name}' fired.",
        priority=1,
        metadata={"trigger_id": trigger.trigger_id, **event_data},
    )
