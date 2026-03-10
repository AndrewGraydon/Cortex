"""OpenWeatherMap adapter — One Call API 3.0 integration.

Uses httpx async client. API key from OPENWEATHERMAP_API_KEY env var.
Caches results for 15 minutes to stay within free tier (1000 calls/day).
"""

from __future__ import annotations

import os
import time
from typing import Any

import structlog

from cortex.external.weather.types import (
    DailyForecast,
    WeatherCondition,
    WeatherData,
    WeatherForecast,
)

logger = structlog.get_logger()

# OpenWeatherMap condition code → WeatherCondition mapping
_CONDITION_MAP: dict[str, WeatherCondition] = {
    "Clear": WeatherCondition.CLEAR,
    "Clouds": WeatherCondition.CLOUDS,
    "Rain": WeatherCondition.RAIN,
    "Drizzle": WeatherCondition.DRIZZLE,
    "Thunderstorm": WeatherCondition.THUNDERSTORM,
    "Snow": WeatherCondition.SNOW,
    "Mist": WeatherCondition.MIST,
    "Fog": WeatherCondition.FOG,
    "Haze": WeatherCondition.MIST,
    "Smoke": WeatherCondition.MIST,
}


class OpenWeatherMapAdapter:
    """OpenWeatherMap One Call API 3.0 adapter.

    Implements ExternalServiceAdapter protocol.
    API key is read from the OPENWEATHERMAP_API_KEY environment variable.
    """

    BASE_URL = "https://api.openweathermap.org/data/3.0/onecall"

    def __init__(
        self,
        latitude: float,
        longitude: float,
        units: str = "metric",
        cache_ttl_seconds: int = 900,
    ) -> None:
        self._lat = latitude
        self._lon = longitude
        self._units = units
        self._cache_ttl = cache_ttl_seconds
        self._client: Any = None
        self._connected = False
        self._cache: WeatherForecast | None = None
        self._cache_time: float = 0.0

    async def connect(self) -> None:
        """Initialize httpx client."""
        try:
            import httpx  # noqa: PLC0415

            self._client = httpx.AsyncClient(timeout=10.0)
            self._connected = True
            logger.info(
                "OpenWeatherMap connected",
                latitude=self._lat,
                longitude=self._lon,
            )
        except Exception:
            self._connected = False
            logger.exception("OpenWeatherMap connection failed")
            raise

    async def disconnect(self) -> None:
        """Close httpx client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._connected = False
        self._cache = None
        logger.info("OpenWeatherMap disconnected")

    async def health_check(self) -> bool:
        """Check if API is reachable."""
        if not self._connected or self._client is None:
            return False
        api_key = os.environ.get("OPENWEATHERMAP_API_KEY", "")
        return bool(api_key)

    @property
    def service_type(self) -> str:
        return "weather"

    async def get_forecast(self) -> WeatherForecast:
        """Get current weather and forecast.

        Returns cached result if within TTL.
        """
        now = time.monotonic()
        if self._cache is not None and (now - self._cache_time) < self._cache_ttl:
            return self._cache

        if self._client is None:
            msg = "Not connected — call connect() first"
            raise RuntimeError(msg)

        api_key = os.environ.get("OPENWEATHERMAP_API_KEY", "")
        if not api_key:
            msg = "OPENWEATHERMAP_API_KEY not set"
            raise RuntimeError(msg)

        params = {
            "lat": self._lat,
            "lon": self._lon,
            "appid": api_key,
            "units": self._units,
            "exclude": "minutely,hourly,alerts",
        }

        try:
            response = await self._client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()
            forecast = _parse_onecall_response(data)
            self._cache = forecast
            self._cache_time = now
            logger.debug("OpenWeatherMap forecast updated")
            return forecast
        except Exception:
            logger.exception("OpenWeatherMap API call failed")
            raise


def _parse_condition(weather_list: list[dict[str, Any]]) -> tuple[WeatherCondition, str]:
    """Parse OWM weather array into condition + description."""
    if not weather_list:
        return WeatherCondition.UNKNOWN, "unknown"
    main = weather_list[0].get("main", "")
    desc = weather_list[0].get("description", "unknown")
    condition = _CONDITION_MAP.get(main, WeatherCondition.UNKNOWN)
    return condition, desc


def _parse_onecall_response(data: dict[str, Any]) -> WeatherForecast:
    """Parse OWM One Call 3.0 response into WeatherForecast."""
    current_data = data.get("current", {})
    condition, description = _parse_condition(current_data.get("weather", []))

    current = WeatherData(
        temperature=current_data.get("temp", 0.0),
        feels_like=current_data.get("feels_like", 0.0),
        humidity=current_data.get("humidity", 0),
        condition=condition,
        description=description,
        wind_speed=current_data.get("wind_speed", 0.0),
        wind_direction=current_data.get("wind_deg", 0),
        pressure=current_data.get("pressure", 1013),
        visibility=current_data.get("visibility", 10000),
        clouds=current_data.get("clouds", 0),
    )

    daily_list: list[DailyForecast] = []
    from datetime import UTC, datetime  # noqa: PLC0415

    for day_data in data.get("daily", [])[:7]:
        day_condition, day_desc = _parse_condition(day_data.get("weather", []))
        temp = day_data.get("temp", {})
        daily_list.append(
            DailyForecast(
                date=datetime.fromtimestamp(day_data.get("dt", 0), tz=UTC),
                temp_high=temp.get("max", 0.0),
                temp_low=temp.get("min", 0.0),
                condition=day_condition,
                description=day_desc,
                pop=day_data.get("pop", 0.0),
            )
        )

    return WeatherForecast(
        current=current,
        daily=daily_list,
        location=f"{data.get('lat', 0)},{data.get('lon', 0)}",
    )
