"""Mock weather adapter — in-memory weather data for testing and offline use."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from cortex.external.weather.types import (
    DailyForecast,
    WeatherCondition,
    WeatherData,
    WeatherForecast,
)

logger = logging.getLogger(__name__)


class MockWeatherAdapter:
    """In-memory weather adapter for testing and development.

    Returns configurable weather data without any API calls.
    Satisfies ExternalServiceAdapter protocol.
    """

    def __init__(
        self,
        temperature: float = 18.0,
        condition: WeatherCondition = WeatherCondition.CLOUDS,
        description: str = "partly cloudy",
    ) -> None:
        self._temperature = temperature
        self._condition = condition
        self._description = description
        self._connected = False
        self._call_count = 0

    async def connect(self) -> None:
        self._connected = True
        logger.info("MockWeatherAdapter connected")

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("MockWeatherAdapter disconnected")

    async def health_check(self) -> bool:
        return self._connected

    @property
    def service_type(self) -> str:
        return "weather"

    async def get_forecast(self) -> WeatherForecast:
        """Return mock weather data."""
        self._call_count += 1
        now = datetime.now(tz=UTC)

        current = WeatherData(
            temperature=self._temperature,
            feels_like=self._temperature - 2,
            humidity=65,
            condition=self._condition,
            description=self._description,
            wind_speed=3.5,
        )

        daily = [
            DailyForecast(
                date=now + timedelta(days=i),
                temp_high=self._temperature + 4 + i,
                temp_low=self._temperature - 6 + i,
                condition=WeatherCondition.CLEAR if i % 2 == 0 else WeatherCondition.CLOUDS,
                description="sunny" if i % 2 == 0 else "partly cloudy",
                pop=0.1 * i,
            )
            for i in range(5)
        ]

        return WeatherForecast(
            current=current,
            daily=daily,
            location="Mock City",
        )

    @property
    def call_count(self) -> int:
        """Number of get_forecast calls (for testing)."""
        return self._call_count
