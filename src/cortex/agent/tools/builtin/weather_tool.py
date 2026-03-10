"""Weather tool — query current conditions and forecast. Tier 0 (safe).

Wired to a weather adapter backend. Falls back to stub responses
if no backend is configured.
"""

from __future__ import annotations

import logging
from typing import Any

from cortex.agent.types import ToolResult

logger = logging.getLogger(__name__)

# Module-level backend — set via set_weather_backend()
_adapter: Any = None


def set_weather_backend(adapter: Any) -> None:
    """Wire the weather tool to a real or mock adapter."""
    global _adapter  # noqa: PLW0603
    _adapter = adapter


def get_weather_backend() -> Any:
    """Get the current weather backend (for testing)."""
    return _adapter


class WeatherQueryTool:
    """Query current weather and forecast. Tier 0 (safe, read-only)."""

    @property
    def name(self) -> str:
        return "weather_query"

    @property
    def description(self) -> str:
        return "Get current weather and forecast"

    @property
    def permission_tier(self) -> int:
        return 0

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "weather_query",
            "description": "Get current weather and forecast",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of forecast days (default 3, max 7)",
                    },
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if _adapter is None:
            return ToolResult(
                tool_name="weather_query",
                success=True,
                data={},
                display_text="Weather is not configured.",
            )

        days = arguments.get("days", 3)
        if not isinstance(days, int) or days < 1:
            days = 3
        days = min(days, 7)

        try:
            forecast = await _adapter.get_forecast()
            display = forecast.format_display(days=days)

            data = {
                "current": {
                    "temperature": forecast.current.temperature,
                    "feels_like": forecast.current.feels_like,
                    "humidity": forecast.current.humidity,
                    "condition": forecast.current.condition.value,
                    "description": forecast.current.description,
                    "wind_speed": forecast.current.wind_speed,
                },
                "daily": [
                    {
                        "date": d.date.isoformat(),
                        "temp_high": d.temp_high,
                        "temp_low": d.temp_low,
                        "condition": d.condition.value,
                        "description": d.description,
                        "pop": d.pop,
                    }
                    for d in forecast.daily[:days]
                ],
                "location": forecast.location,
            }

            return ToolResult(
                tool_name="weather_query",
                success=True,
                data=data,
                display_text=display,
            )
        except Exception as e:
            logger.exception("Weather query failed")
            return ToolResult(
                tool_name="weather_query",
                success=False,
                error=str(e),
            )
