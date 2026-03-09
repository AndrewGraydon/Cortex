"""Tests for power service."""

from __future__ import annotations

from cortex.hal.power.service import MockPowerService, _determine_profile
from cortex.hal.power.types import PowerProfile


class TestDetermineProfile:
    def test_charging_is_mains(self) -> None:
        assert _determine_profile(50.0, is_charging=True) == PowerProfile.MAINS

    def test_charging_low_is_mains(self) -> None:
        assert _determine_profile(5.0, is_charging=True) == PowerProfile.MAINS

    def test_not_charging_high_is_battery(self) -> None:
        assert _determine_profile(80.0, is_charging=False) == PowerProfile.BATTERY

    def test_not_charging_low_is_low_battery(self) -> None:
        assert _determine_profile(15.0, is_charging=False) == PowerProfile.LOW_BATTERY

    def test_not_charging_critical(self) -> None:
        assert _determine_profile(3.0, is_charging=False) == PowerProfile.CRITICAL

    def test_boundary_low_battery(self) -> None:
        assert _determine_profile(20.0, is_charging=False) == PowerProfile.LOW_BATTERY

    def test_boundary_critical(self) -> None:
        assert _determine_profile(5.0, is_charging=False) == PowerProfile.CRITICAL

    def test_just_above_low(self) -> None:
        assert _determine_profile(21.0, is_charging=False) == PowerProfile.BATTERY


class TestMockPowerService:
    async def test_start_stop(self) -> None:
        service = MockPowerService()
        await service.start()
        await service.stop()

    async def test_default_state(self) -> None:
        service = MockPowerService()
        state = await service.get_state()
        assert state.profile == PowerProfile.MAINS
        assert state.battery_percent == 100.0

    async def test_set_state_battery(self) -> None:
        service = MockPowerService()
        service.set_state(battery_percent=80.0, is_charging=False)
        state = await service.get_state()
        assert state.profile == PowerProfile.BATTERY

    async def test_transition_recorded(self) -> None:
        service = MockPowerService()
        transition = service.set_state(battery_percent=80.0, is_charging=False)
        assert transition is not None
        assert transition.from_profile == PowerProfile.MAINS
        assert transition.to_profile == PowerProfile.BATTERY

    async def test_no_transition_same_profile(self) -> None:
        service = MockPowerService()
        transition = service.set_state(battery_percent=100.0, is_charging=True)
        assert transition is None

    async def test_transitions_list(self) -> None:
        service = MockPowerService()
        service.set_state(battery_percent=80.0, is_charging=False)
        service.set_state(battery_percent=10.0, is_charging=False)
        assert len(service.transitions) == 2
