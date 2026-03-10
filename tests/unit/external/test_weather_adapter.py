"""Tests for weather adapters (mock and OpenWeatherMap parser)."""

from __future__ import annotations

from cortex.external.protocols import ExternalServiceAdapter
from cortex.external.weather.mock import MockWeatherAdapter
from cortex.external.weather.openweathermap import (
    _parse_condition,
    _parse_onecall_response,
)
from cortex.external.weather.types import (
    DailyForecast,
    WeatherCondition,
    WeatherData,
    WeatherForecast,
)

# --- WeatherData types ---


class TestWeatherDataTypes:
    def test_weather_data_format_display(self) -> None:
        data = WeatherData(
            temperature=18.0,
            feels_like=16.0,
            humidity=65,
            condition=WeatherCondition.CLOUDS,
            description="partly cloudy",
            wind_speed=3.5,
        )
        display = data.format_display()
        assert "18°C" in display
        assert "partly cloudy" in display
        assert "16°C" in display
        assert "65%" in display

    def test_daily_forecast_format_display(self) -> None:
        from datetime import UTC, datetime

        forecast = DailyForecast(
            date=datetime(2025, 6, 15, tzinfo=UTC),
            temp_high=25.0,
            temp_low=15.0,
            condition=WeatherCondition.CLEAR,
            description="clear sky",
        )
        display = forecast.format_display()
        assert "Sunday" in display
        assert "25°C" in display
        assert "15°C" in display
        assert "clear sky" in display

    def test_daily_forecast_with_precipitation(self) -> None:
        from datetime import UTC, datetime

        forecast = DailyForecast(
            date=datetime(2025, 6, 15, tzinfo=UTC),
            temp_high=20.0,
            temp_low=12.0,
            condition=WeatherCondition.RAIN,
            description="light rain",
            pop=0.65,
        )
        display = forecast.format_display()
        assert "precipitation" in display

    def test_daily_forecast_low_precipitation_hidden(self) -> None:
        from datetime import UTC, datetime

        forecast = DailyForecast(
            date=datetime(2025, 6, 15, tzinfo=UTC),
            temp_high=20.0,
            temp_low=12.0,
            condition=WeatherCondition.CLOUDS,
            description="overcast",
            pop=0.1,
        )
        display = forecast.format_display()
        assert "precipitation" not in display

    def test_weather_forecast_format_display(self) -> None:
        from datetime import UTC, datetime

        current = WeatherData(
            temperature=18.0,
            feels_like=16.0,
            humidity=65,
            condition=WeatherCondition.CLOUDS,
            description="partly cloudy",
            wind_speed=3.5,
        )
        daily = [
            DailyForecast(
                date=datetime(2025, 6, 15, tzinfo=UTC),
                temp_high=22.0,
                temp_low=12.0,
                condition=WeatherCondition.CLEAR,
                description="sunny",
            ),
            DailyForecast(
                date=datetime(2025, 6, 16, tzinfo=UTC),
                temp_high=24.0,
                temp_low=14.0,
                condition=WeatherCondition.CLOUDS,
                description="partly cloudy",
            ),
        ]
        forecast = WeatherForecast(current=current, daily=daily, location="Test City")
        display = forecast.format_display(days=2)
        assert "18°C" in display
        assert "sunny" in display

    def test_weather_forecast_format_limits_days(self) -> None:
        from datetime import UTC, datetime

        current = WeatherData(
            temperature=20.0,
            feels_like=18.0,
            humidity=50,
            condition=WeatherCondition.CLEAR,
            description="clear",
            wind_speed=2.0,
        )
        daily = [
            DailyForecast(
                date=datetime(2025, 6, i + 15, tzinfo=UTC),
                temp_high=20.0 + i,
                temp_low=10.0 + i,
                condition=WeatherCondition.CLEAR,
                description=f"day{i}",
            )
            for i in range(5)
        ]
        forecast = WeatherForecast(current=current, daily=daily)
        display = forecast.format_display(days=1)
        assert "day0" in display
        assert "day1" not in display

    def test_weather_condition_values(self) -> None:
        assert WeatherCondition.CLEAR.value == "clear"
        assert WeatherCondition.THUNDERSTORM.value == "thunderstorm"
        assert WeatherCondition.UNKNOWN.value == "unknown"


# --- MockWeatherAdapter ---


class TestMockWeatherAdapterProtocol:
    def test_satisfies_external_service_adapter(self) -> None:
        adapter = MockWeatherAdapter()
        assert isinstance(adapter, ExternalServiceAdapter)

    def test_service_type(self) -> None:
        adapter = MockWeatherAdapter()
        assert adapter.service_type == "weather"


class TestMockWeatherAdapterLifecycle:
    async def test_connect(self) -> None:
        adapter = MockWeatherAdapter()
        await adapter.connect()
        assert adapter._connected is True

    async def test_disconnect(self) -> None:
        adapter = MockWeatherAdapter()
        await adapter.connect()
        await adapter.disconnect()
        assert adapter._connected is False

    async def test_health_check_connected(self) -> None:
        adapter = MockWeatherAdapter()
        await adapter.connect()
        assert await adapter.health_check() is True

    async def test_health_check_disconnected(self) -> None:
        adapter = MockWeatherAdapter()
        assert await adapter.health_check() is False


class TestMockWeatherAdapterForecast:
    async def test_get_forecast_returns_data(self) -> None:
        adapter = MockWeatherAdapter()
        forecast = await adapter.get_forecast()
        assert isinstance(forecast, WeatherForecast)
        assert forecast.current.temperature == 18.0
        assert len(forecast.daily) == 5

    async def test_custom_temperature(self) -> None:
        adapter = MockWeatherAdapter(temperature=25.0)
        forecast = await adapter.get_forecast()
        assert forecast.current.temperature == 25.0

    async def test_custom_condition(self) -> None:
        adapter = MockWeatherAdapter(
            condition=WeatherCondition.RAIN,
            description="heavy rain",
        )
        forecast = await adapter.get_forecast()
        assert forecast.current.condition == WeatherCondition.RAIN
        assert forecast.current.description == "heavy rain"

    async def test_call_count(self) -> None:
        adapter = MockWeatherAdapter()
        assert adapter.call_count == 0
        await adapter.get_forecast()
        await adapter.get_forecast()
        assert adapter.call_count == 2

    async def test_forecast_location(self) -> None:
        adapter = MockWeatherAdapter()
        forecast = await adapter.get_forecast()
        assert forecast.location == "Mock City"


# --- OpenWeatherMap parser ---


class TestOWMParser:
    def test_parse_condition_clear(self) -> None:
        condition, desc = _parse_condition([{"main": "Clear", "description": "clear sky"}])
        assert condition == WeatherCondition.CLEAR
        assert desc == "clear sky"

    def test_parse_condition_rain(self) -> None:
        condition, desc = _parse_condition([{"main": "Rain", "description": "light rain"}])
        assert condition == WeatherCondition.RAIN

    def test_parse_condition_unknown(self) -> None:
        condition, desc = _parse_condition([{"main": "Tornado", "description": "tornado"}])
        assert condition == WeatherCondition.UNKNOWN

    def test_parse_condition_empty(self) -> None:
        condition, desc = _parse_condition([])
        assert condition == WeatherCondition.UNKNOWN
        assert desc == "unknown"

    def test_parse_onecall_response(self) -> None:
        data = {
            "lat": 51.5,
            "lon": -0.1,
            "current": {
                "temp": 15.3,
                "feels_like": 13.1,
                "humidity": 72,
                "wind_speed": 4.1,
                "wind_deg": 180,
                "pressure": 1015,
                "visibility": 10000,
                "clouds": 40,
                "weather": [{"main": "Clouds", "description": "scattered clouds"}],
            },
            "daily": [
                {
                    "dt": 1718400000,
                    "temp": {"max": 20.0, "min": 12.0},
                    "weather": [{"main": "Clear", "description": "clear sky"}],
                    "pop": 0.1,
                },
                {
                    "dt": 1718486400,
                    "temp": {"max": 22.0, "min": 14.0},
                    "weather": [{"main": "Rain", "description": "light rain"}],
                    "pop": 0.6,
                },
            ],
        }
        forecast = _parse_onecall_response(data)
        assert forecast.current.temperature == 15.3
        assert forecast.current.humidity == 72
        assert forecast.current.condition == WeatherCondition.CLOUDS
        assert len(forecast.daily) == 2
        assert forecast.daily[0].temp_high == 20.0
        assert forecast.daily[1].condition == WeatherCondition.RAIN
        assert forecast.location == "51.5,-0.1"

    def test_parse_onecall_empty(self) -> None:
        forecast = _parse_onecall_response({})
        assert forecast.current.temperature == 0.0
        assert len(forecast.daily) == 0

    def test_parse_onecall_limits_daily_to_7(self) -> None:
        data = {
            "current": {
                "temp": 15.0,
                "feels_like": 13.0,
                "humidity": 50,
                "wind_speed": 2.0,
                "weather": [{"main": "Clear", "description": "clear"}],
            },
            "daily": [
                {
                    "dt": 1718400000 + i * 86400,
                    "temp": {"max": 20.0, "min": 10.0},
                    "weather": [{"main": "Clear", "description": "clear"}],
                }
                for i in range(10)
            ],
        }
        forecast = _parse_onecall_response(data)
        assert len(forecast.daily) == 7
