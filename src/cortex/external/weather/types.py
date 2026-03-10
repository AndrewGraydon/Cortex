"""Weather data types — conditions, forecasts, and current weather."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime


class WeatherCondition(enum.Enum):
    """High-level weather condition categories."""

    CLEAR = "clear"
    CLOUDS = "clouds"
    RAIN = "rain"
    DRIZZLE = "drizzle"
    THUNDERSTORM = "thunderstorm"
    SNOW = "snow"
    MIST = "mist"
    FOG = "fog"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class WeatherData:
    """Current weather observation."""

    temperature: float  # Celsius
    feels_like: float  # Celsius
    humidity: int  # Percentage 0-100
    condition: WeatherCondition
    description: str  # e.g. "partly cloudy"
    wind_speed: float  # m/s
    wind_direction: int = 0  # Degrees
    pressure: int = 1013  # hPa
    visibility: int = 10000  # metres
    clouds: int = 0  # Percentage 0-100
    timestamp: datetime | None = None

    def format_display(self) -> str:
        """Format for TTS or text display."""
        return (
            f"Currently {self.temperature:.0f}°C and {self.description}. "
            f"Feels like {self.feels_like:.0f}°C, "
            f"humidity {self.humidity}%."
        )


@dataclass(frozen=True)
class DailyForecast:
    """Single day forecast."""

    date: datetime
    temp_high: float  # Celsius
    temp_low: float  # Celsius
    condition: WeatherCondition
    description: str
    pop: float = 0.0  # Probability of precipitation 0-1

    def format_display(self) -> str:
        """Format for TTS or text display."""
        day_name = self.date.strftime("%A")
        precip = f", {self.pop:.0%} chance of precipitation" if self.pop > 0.2 else ""
        return (
            f"{day_name}: {self.description}, "
            f"high {self.temp_high:.0f}°C, low {self.temp_low:.0f}°C{precip}"
        )


@dataclass(frozen=True)
class WeatherForecast:
    """Weather forecast containing current conditions and daily predictions."""

    current: WeatherData
    daily: list[DailyForecast] = field(default_factory=list)
    location: str = ""

    def format_display(self, days: int = 3) -> str:
        """Format current + forecast for TTS."""
        parts = [self.current.format_display()]
        for day in self.daily[:days]:
            parts.append(day.format_display())
        return " ".join(parts)
