"""Tests for DeviceResolver — natural language device name resolution."""

from __future__ import annotations

import pytest

from cortex.iot.registry import DeviceRegistry
from cortex.iot.resolver import DeviceResolver
from cortex.iot.types import DeviceCategory, DeviceInfo, DeviceSource


@pytest.fixture()
async def registry() -> DeviceRegistry:
    """Create a registry with test devices."""
    reg = DeviceRegistry()
    await reg.initialize()

    devices = [
        DeviceInfo(
            id="light.kitchen",
            name="Kitchen Light",
            friendly_name="Kitchen Light",
            category=DeviceCategory.LIGHT,
            room="kitchen",
            source=DeviceSource.HOMEASSISTANT,
        ),
        DeviceInfo(
            id="light.living_room",
            name="Living Room Light",
            friendly_name="Living Room Light",
            category=DeviceCategory.LIGHT,
            room="living_room",
            source=DeviceSource.HOMEASSISTANT,
        ),
        DeviceInfo(
            id="light.bedroom_lamp",
            name="Bedroom Lamp",
            friendly_name="Bedroom Lamp",
            category=DeviceCategory.LIGHT,
            room="bedroom",
            source=DeviceSource.HOMEASSISTANT,
        ),
        DeviceInfo(
            id="switch.kitchen_plug",
            name="Kitchen Plug",
            friendly_name="Kitchen Plug",
            category=DeviceCategory.SWITCH,
            room="kitchen",
            source=DeviceSource.HOMEASSISTANT,
        ),
        DeviceInfo(
            id="climate.thermostat",
            name="Thermostat",
            friendly_name="Thermostat",
            category=DeviceCategory.CLIMATE,
            room="living_room",
            source=DeviceSource.HOMEASSISTANT,
        ),
    ]
    for d in devices:
        await reg.register_device(d)
    return reg


@pytest.fixture()
async def resolver(registry: DeviceRegistry) -> DeviceResolver:
    return DeviceResolver(registry)


class TestExactMatch:
    def test_exact_friendly_name(self, resolver: DeviceResolver) -> None:
        result = resolver.resolve("Kitchen Light")
        assert result.matched
        assert result.best is not None
        assert result.best.id == "light.kitchen"
        assert result.candidates[0].confidence == 1.0
        assert result.candidates[0].match_type == "exact"

    def test_exact_name_case_insensitive(self, resolver: DeviceResolver) -> None:
        result = resolver.resolve("kitchen light")
        assert result.matched
        assert result.best is not None
        assert result.best.id == "light.kitchen"

    def test_exact_id(self, resolver: DeviceResolver) -> None:
        result = resolver.resolve("light.kitchen")
        assert result.matched
        assert result.best is not None
        assert result.best.id == "light.kitchen"

    def test_exact_no_match(self, resolver: DeviceResolver) -> None:
        result = resolver.resolve("Garage Door")
        assert not result.matched
        assert result.best is None


class TestFuzzyMatch:
    def test_partial_name(self, resolver: DeviceResolver) -> None:
        result = resolver.resolve("kitchen")
        assert len(result.candidates) >= 1
        # Should find kitchen light and kitchen plug
        device_ids = [c.device.id for c in result.candidates]
        assert "light.kitchen" in device_ids
        assert "switch.kitchen_plug" in device_ids

    def test_room_token(self, resolver: DeviceResolver) -> None:
        result = resolver.resolve("bedroom")
        assert len(result.candidates) >= 1
        assert result.candidates[0].device.id == "light.bedroom_lamp"
        assert result.candidates[0].match_type == "fuzzy"

    def test_fuzzy_confidence_range(self, resolver: DeviceResolver) -> None:
        result = resolver.resolve("kitchen")
        for c in result.candidates:
            assert 0.5 <= c.confidence <= 0.9

    def test_ambiguous_result(self, resolver: DeviceResolver) -> None:
        result = resolver.resolve("kitchen")
        # Both kitchen light and kitchen plug have similar confidence
        if len(result.candidates) > 1:
            gap = result.candidates[0].confidence - result.candidates[1].confidence
            if gap < 0.1:
                assert result.ambiguous


class TestCategoryRoomMatch:
    def test_category_only(self, resolver: DeviceResolver) -> None:
        result = resolver.resolve("thermostat")
        assert result.best is not None
        assert result.best.id == "climate.thermostat"

    def test_category_alias(self, resolver: DeviceResolver) -> None:
        result = resolver.resolve("plug")
        assert len(result.candidates) >= 1
        categories = [c.device.category for c in result.candidates]
        assert DeviceCategory.SWITCH in categories

    def test_category_with_room(self, resolver: DeviceResolver) -> None:
        result = resolver.resolve("kitchen lights")
        assert len(result.candidates) >= 1
        # Should find kitchen light with higher confidence
        best = result.candidates[0]
        assert best.device.room == "kitchen"

    def test_lamp_alias(self, resolver: DeviceResolver) -> None:
        result = resolver.resolve("lamp")
        assert len(result.candidates) >= 1
        categories = [c.device.category for c in result.candidates]
        assert DeviceCategory.LIGHT in categories


class TestEdgeCases:
    def test_empty_query(self, resolver: DeviceResolver) -> None:
        result = resolver.resolve("")
        assert not result.matched
        assert len(result.candidates) == 0

    def test_whitespace_query(self, resolver: DeviceResolver) -> None:
        result = resolver.resolve("   ")
        assert not result.matched

    def test_single_candidate_not_ambiguous(self, resolver: DeviceResolver) -> None:
        result = resolver.resolve("Thermostat")
        assert not result.ambiguous

    def test_resolve_result_properties(self, resolver: DeviceResolver) -> None:
        result = resolver.resolve("Kitchen Light")
        assert result.matched is True
        assert result.ambiguous is False
        assert result.best is not None
        assert result.best.friendly_name == "Kitchen Light"
