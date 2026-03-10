"""Tests for weather query tool."""

from __future__ import annotations

import pytest

from cortex.agent.tools.builtin.weather_tool import (
    WeatherQueryTool,
    get_weather_backend,
    set_weather_backend,
)
from cortex.external.weather.mock import MockWeatherAdapter
from cortex.external.weather.types import WeatherCondition


@pytest.fixture(autouse=True)
def _reset_backend() -> None:  # type: ignore[misc]
    """Reset the weather backend between tests."""
    set_weather_backend(None)
    yield  # type: ignore[misc]
    set_weather_backend(None)


class TestWeatherQueryToolSchema:
    def test_name(self) -> None:
        tool = WeatherQueryTool()
        assert tool.name == "weather_query"

    def test_tier(self) -> None:
        tool = WeatherQueryTool()
        assert tool.permission_tier == 0

    def test_schema(self) -> None:
        tool = WeatherQueryTool()
        schema = tool.get_schema()
        assert schema["name"] == "weather_query"
        assert "days" in schema["parameters"]["properties"]


class TestWeatherQueryToolNoBackend:
    async def test_no_backend_returns_not_configured(self) -> None:
        tool = WeatherQueryTool()
        result = await tool.execute({})
        assert result.success is True
        assert "not configured" in result.display_text


class TestWeatherQueryToolWithBackend:
    async def test_basic_query(self) -> None:
        adapter = MockWeatherAdapter()
        set_weather_backend(adapter)

        tool = WeatherQueryTool()
        result = await tool.execute({})
        assert result.success is True
        assert "18°C" in result.display_text
        assert result.data["current"]["temperature"] == 18.0

    async def test_custom_days(self) -> None:
        adapter = MockWeatherAdapter()
        set_weather_backend(adapter)

        tool = WeatherQueryTool()
        result = await tool.execute({"days": 2})
        assert result.success is True
        assert len(result.data["daily"]) == 2

    async def test_days_capped_at_7(self) -> None:
        adapter = MockWeatherAdapter()
        set_weather_backend(adapter)

        tool = WeatherQueryTool()
        result = await tool.execute({"days": 20})
        assert result.success is True
        assert len(result.data["daily"]) <= 7

    async def test_invalid_days_defaults_to_3(self) -> None:
        adapter = MockWeatherAdapter()
        set_weather_backend(adapter)

        tool = WeatherQueryTool()
        result = await tool.execute({"days": -1})
        assert result.success is True
        assert len(result.data["daily"]) == 3

    async def test_data_structure(self) -> None:
        adapter = MockWeatherAdapter()
        set_weather_backend(adapter)

        tool = WeatherQueryTool()
        result = await tool.execute({})
        assert "current" in result.data
        assert "daily" in result.data
        assert "location" in result.data
        assert "temperature" in result.data["current"]
        assert "condition" in result.data["current"]

    async def test_custom_weather(self) -> None:
        adapter = MockWeatherAdapter(
            temperature=30.0,
            condition=WeatherCondition.CLEAR,
            description="clear sky",
        )
        set_weather_backend(adapter)

        tool = WeatherQueryTool()
        result = await tool.execute({})
        assert result.data["current"]["temperature"] == 30.0
        assert "clear sky" in result.display_text

    async def test_backend_error(self) -> None:
        class FailingAdapter:
            async def get_forecast(self) -> None:
                msg = "API error"
                raise RuntimeError(msg)

        set_weather_backend(FailingAdapter())
        tool = WeatherQueryTool()
        result = await tool.execute({})
        assert result.success is False
        assert "API error" in (result.error or "")

    async def test_set_get_backend(self) -> None:
        adapter = MockWeatherAdapter()
        set_weather_backend(adapter)
        assert get_weather_backend() is adapter
