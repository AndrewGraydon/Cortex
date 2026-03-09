"""Tests for power types."""

from __future__ import annotations

from cortex.hal.power.types import (
    CRITICAL_THRESHOLD,
    LOW_BATTERY_THRESHOLD,
    PowerProfile,
    PowerState,
    PowerTransition,
)


class TestPowerProfile:
    def test_mains_value(self) -> None:
        assert PowerProfile.MAINS.value == "mains"

    def test_battery_value(self) -> None:
        assert PowerProfile.BATTERY.value == "battery"

    def test_low_battery_value(self) -> None:
        assert PowerProfile.LOW_BATTERY.value == "low_battery"

    def test_critical_value(self) -> None:
        assert PowerProfile.CRITICAL.value == "critical"


class TestPowerState:
    def test_defaults(self) -> None:
        state = PowerState()
        assert state.profile == PowerProfile.MAINS
        assert state.battery_percent == 100.0
        assert state.is_charging is True
        assert state.voltage == 5.0
        assert state.timestamp > 0

    def test_custom_values(self) -> None:
        state = PowerState(
            profile=PowerProfile.LOW_BATTERY,
            battery_percent=15.0,
            is_charging=False,
            voltage=3.7,
        )
        assert state.profile == PowerProfile.LOW_BATTERY
        assert state.battery_percent == 15.0


class TestPowerTransition:
    def test_transition(self) -> None:
        t = PowerTransition(
            from_profile=PowerProfile.MAINS,
            to_profile=PowerProfile.BATTERY,
            battery_percent=95.0,
        )
        assert t.from_profile == PowerProfile.MAINS
        assert t.to_profile == PowerProfile.BATTERY
        assert t.timestamp > 0


class TestThresholds:
    def test_low_battery_threshold(self) -> None:
        assert LOW_BATTERY_THRESHOLD == 20.0

    def test_critical_threshold(self) -> None:
        assert CRITICAL_THRESHOLD == 5.0
