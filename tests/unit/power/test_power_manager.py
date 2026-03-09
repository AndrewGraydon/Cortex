"""Tests for power profile manager."""

from __future__ import annotations

from cortex.hal.power.manager import PROFILE_SETTINGS, PowerProfileManager
from cortex.hal.power.types import PowerProfile, PowerState, PowerTransition


class TestGetSettings:
    def test_mains_settings(self) -> None:
        manager = PowerProfileManager()
        settings = manager.get_settings()
        assert settings["model"] == "qwen3-vl-2b"
        assert settings["brightness"] == 80

    def test_battery_settings(self) -> None:
        manager = PowerProfileManager()
        settings = manager.get_settings(PowerProfile.BATTERY)
        assert settings["brightness"] == 50

    def test_critical_settings(self) -> None:
        settings = PROFILE_SETTINGS[PowerProfile.CRITICAL]
        assert settings["model"] is None
        assert settings["proactive_enabled"] is False


class TestApplyTransition:
    def test_transition_changes_profile(self) -> None:
        manager = PowerProfileManager()
        transition = PowerTransition(
            from_profile=PowerProfile.MAINS,
            to_profile=PowerProfile.BATTERY,
            battery_percent=80.0,
        )
        manager.apply_transition(transition)
        assert manager.current_profile == PowerProfile.BATTERY

    def test_transition_returns_settings(self) -> None:
        manager = PowerProfileManager()
        transition = PowerTransition(
            from_profile=PowerProfile.MAINS,
            to_profile=PowerProfile.BATTERY,
            battery_percent=80.0,
        )
        settings = manager.apply_transition(transition)
        assert settings["brightness"] == 50

    def test_transition_recorded(self) -> None:
        manager = PowerProfileManager()
        transition = PowerTransition(
            from_profile=PowerProfile.MAINS,
            to_profile=PowerProfile.BATTERY,
            battery_percent=80.0,
        )
        manager.apply_transition(transition)
        assert len(manager.transition_history) == 1


class TestManualOverride:
    def test_override_changes_profile(self) -> None:
        manager = PowerProfileManager()
        manager.set_override(PowerProfile.LOW_BATTERY)
        assert manager.current_profile == PowerProfile.LOW_BATTERY
        assert manager.is_overridden is True

    def test_override_returns_settings(self) -> None:
        manager = PowerProfileManager()
        settings = manager.set_override(PowerProfile.LOW_BATTERY)
        assert settings["brightness"] == 20

    def test_override_blocks_transitions(self) -> None:
        manager = PowerProfileManager()
        manager.set_override(PowerProfile.MAINS)
        transition = PowerTransition(
            from_profile=PowerProfile.MAINS,
            to_profile=PowerProfile.CRITICAL,
            battery_percent=3.0,
        )
        manager.apply_transition(transition)
        assert manager.current_profile == PowerProfile.MAINS

    def test_clear_override(self) -> None:
        manager = PowerProfileManager()
        manager.set_override(PowerProfile.LOW_BATTERY)
        manager.clear_override()
        assert manager.is_overridden is False
        assert manager.current_profile == PowerProfile.MAINS


class TestUpdateFromState:
    def test_state_triggers_transition(self) -> None:
        manager = PowerProfileManager()
        state = PowerState(profile=PowerProfile.BATTERY, battery_percent=80.0, is_charging=False)
        settings = manager.update_from_state(state)
        assert settings is not None
        assert manager.current_profile == PowerProfile.BATTERY

    def test_same_state_no_transition(self) -> None:
        manager = PowerProfileManager()
        state = PowerState(profile=PowerProfile.MAINS, battery_percent=100.0, is_charging=True)
        settings = manager.update_from_state(state)
        assert settings is None

    def test_auto_switch_disabled(self) -> None:
        manager = PowerProfileManager(auto_switch=False)
        state = PowerState(profile=PowerProfile.CRITICAL, battery_percent=3.0, is_charging=False)
        settings = manager.update_from_state(state)
        assert settings is None
        assert manager.current_profile == PowerProfile.MAINS
