"""Clock tool — current time/date. Tier 0 (safe)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from cortex.agent.types import ToolResult


class ClockTool:
    """Returns current time and date."""

    @property
    def name(self) -> str:
        return "clock"

    @property
    def description(self) -> str:
        return "Get current time/date"

    @property
    def permission_tier(self) -> int:
        return 0

    def __init__(self, timezone: str = "UTC") -> None:
        self._timezone = timezone

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "clock",
            "description": "Get current time/date",
            "parameters": {
                "type": "object",
                "properties": {
                    "format": {
                        "type": "string",
                        "description": "time, date, or both",
                    },
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        fmt = arguments.get("format", "both")
        now = datetime.now(tz=ZoneInfo(self._timezone))

        if fmt == "time":
            text = now.strftime("%-I:%M %p")
        elif fmt == "date":
            text = now.strftime("%A, %B %-d, %Y")
        else:
            text = now.strftime("%-I:%M %p on %A, %B %-d, %Y")

        return ToolResult(
            tool_name="clock",
            success=True,
            data=now.isoformat(),
            display_text=f"It's {text}.",
        )
