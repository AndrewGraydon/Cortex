"""Timer tools — set, query, cancel timers. Tier 0-1."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from cortex.agent.types import ToolResult


@dataclass
class Timer:
    """An active timer."""

    id: str
    label: str
    duration_seconds: int
    created_at: float
    fires_at: float
    status: str = "active"  # active, fired, cancelled


class TimerStore:
    """In-memory timer storage. Replaced by SchedulingService in Milestone 2.7."""

    def __init__(self, max_timers: int = 20) -> None:
        self._timers: dict[str, Timer] = {}
        self._max_timers = max_timers

    def create(self, duration: int, label: str = "") -> Timer:
        active = [t for t in self._timers.values() if t.status == "active"]
        if len(active) >= self._max_timers:
            msg = f"Maximum {self._max_timers} active timers reached"
            raise ValueError(msg)
        now = time.time()
        timer = Timer(
            id=uuid.uuid4().hex[:8],
            label=label or f"{duration}s timer",
            duration_seconds=duration,
            created_at=now,
            fires_at=now + duration,
        )
        self._timers[timer.id] = timer
        return timer

    def get_active(self) -> list[Timer]:
        return [t for t in self._timers.values() if t.status == "active"]

    def cancel(self, timer_id: str) -> Timer | None:
        timer = self._timers.get(timer_id)
        if timer and timer.status == "active":
            timer.status = "cancelled"
            return timer
        return None

    def cancel_by_label(self, label: str) -> Timer | None:
        for timer in self._timers.values():
            if timer.status == "active" and label.lower() in timer.label.lower():
                timer.status = "cancelled"
                return timer
        return None


# Shared timer store — replaced by DI in service layer
_default_store = TimerStore()


def get_timer_store() -> TimerStore:
    return _default_store


def set_timer_store(store: TimerStore) -> None:
    global _default_store
    _default_store = store


class TimerSetTool:
    """Set a countdown timer."""

    @property
    def name(self) -> str:
        return "timer_set"

    @property
    def description(self) -> str:
        return "Set countdown timer"

    @property
    def permission_tier(self) -> int:
        return 1  # Logged

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "timer_set",
            "description": "Set countdown timer",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration": {
                        "type": "integer",
                        "description": "Duration in seconds",
                    },
                    "label": {
                        "type": "string",
                        "description": "Timer label",
                    },
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        duration = arguments.get("duration")
        if not duration or not isinstance(duration, (int, float)):
            return ToolResult(
                tool_name="timer_set",
                success=False,
                error="Duration is required (in seconds)",
            )
        duration = int(duration)
        if duration <= 0 or duration > 86400:
            return ToolResult(
                tool_name="timer_set",
                success=False,
                error="Duration must be 1-86400 seconds",
            )
        label = arguments.get("label", "")
        try:
            timer = get_timer_store().create(duration, label)
        except ValueError as e:
            return ToolResult(tool_name="timer_set", success=False, error=str(e))

        # Format for speech
        if duration >= 3600:
            h = duration // 3600
            m = (duration % 3600) // 60
            time_str = f"{h} hour{'s' if h > 1 else ''}"
            if m:
                time_str += f" {m} minute{'s' if m > 1 else ''}"
        elif duration >= 60:
            m = duration // 60
            s = duration % 60
            time_str = f"{m} minute{'s' if m > 1 else ''}"
            if s:
                time_str += f" {s} second{'s' if s > 1 else ''}"
        else:
            time_str = f"{duration} second{'s' if duration > 1 else ''}"

        name = f" '{timer.label}'" if label else ""
        return ToolResult(
            tool_name="timer_set",
            success=True,
            data={"timer_id": timer.id, "fires_at": timer.fires_at},
            display_text=f"Timer{name} set for {time_str}.",
        )


class TimerQueryTool:
    """Query active timers."""

    @property
    def name(self) -> str:
        return "timer_query"

    @property
    def description(self) -> str:
        return "List active timers"

    @property
    def permission_tier(self) -> int:
        return 0

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "timer_query",
            "description": "List active timers",
            "parameters": {"type": "object", "properties": {}},
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        timers = get_timer_store().get_active()
        if not timers:
            return ToolResult(
                tool_name="timer_query",
                success=True,
                data=[],
                display_text="No active timers.",
            )
        now = time.time()
        parts = []
        for t in timers:
            remaining = max(0, int(t.fires_at - now))
            m, s = divmod(remaining, 60)
            parts.append(f"{t.label}: {m}m {s}s remaining")
        return ToolResult(
            tool_name="timer_query",
            success=True,
            data=[{"id": t.id, "label": t.label} for t in timers],
            display_text=". ".join(parts) + ".",
        )


class TimerCancelTool:
    """Cancel an active timer."""

    @property
    def name(self) -> str:
        return "timer_cancel"

    @property
    def description(self) -> str:
        return "Cancel a timer by label"

    @property
    def permission_tier(self) -> int:
        return 1  # Logged

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "timer_cancel",
            "description": "Cancel a timer by label",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Timer label to cancel",
                    },
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        label = arguments.get("label", "")
        if not label:
            return ToolResult(
                tool_name="timer_cancel",
                success=False,
                error="Timer label required",
            )
        timer = get_timer_store().cancel_by_label(label)
        if timer:
            return ToolResult(
                tool_name="timer_cancel",
                success=True,
                data={"timer_id": timer.id},
                display_text=f"Timer '{timer.label}' cancelled.",
            )
        return ToolResult(
            tool_name="timer_cancel",
            success=False,
            error=f"No active timer matching '{label}'",
        )
