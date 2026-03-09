"""Proactive types — patterns, candidates, and types."""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any


class ProactiveType(enum.Enum):
    """Types of proactive actions."""

    ROUTINE_REMINDER = "routine_reminder"
    MORNING_BRIEFING = "morning_briefing"
    PATTERN_ALERT = "pattern_alert"


@dataclass
class RoutinePattern:
    """A detected routine pattern from episodic data."""

    event_type: str
    content: str
    hour: int
    day_of_week: int  # 0=Monday
    count: int
    confidence: float = 0.0


@dataclass
class ProactiveCandidate:
    """A candidate proactive action to be delivered."""

    proactive_type: ProactiveType
    title: str
    message: str
    priority: int = 2  # 1=urgent, 2=normal, 3=low
    pattern: RoutinePattern | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
