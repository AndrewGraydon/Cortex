"""Power profile manager — orchestrates profile transitions.

Handles model swapping, display brightness, polling interval, and proactive
engine toggling based on current power profile.
"""

from __future__ import annotations

import logging
from typing import Any

from cortex.hal.power.types import PowerProfile, PowerState, PowerTransition

logger = logging.getLogger(__name__)

# Default settings per profile
PROFILE_SETTINGS: dict[PowerProfile, dict[str, Any]] = {
    PowerProfile.MAINS: {
        "model": "qwen3-vl-2b",
        "brightness": 80,
        "poll_interval": 10,
        "proactive_enabled": True,
    },
    PowerProfile.BATTERY: {
        "model": "qwen3-vl-2b",
        "brightness": 50,
        "poll_interval": 30,
        "proactive_enabled": True,
    },
    PowerProfile.LOW_BATTERY: {
        "model": "qwen3-0.6b",
        "brightness": 20,
        "poll_interval": 60,
        "proactive_enabled": False,
    },
    PowerProfile.CRITICAL: {
        "model": None,  # No LLM, regex-only
        "brightness": 10,
        "poll_interval": 120,
        "proactive_enabled": False,
    },
}


class PowerProfileManager:
    """Manages power profile transitions and settings."""

    def __init__(self, auto_switch: bool = True) -> None:
        self._auto_switch = auto_switch
        self._current_profile = PowerProfile.MAINS
        self._manual_override: PowerProfile | None = None
        self._transition_history: list[PowerTransition] = []

    @property
    def current_profile(self) -> PowerProfile:
        return self._manual_override or self._current_profile

    @property
    def auto_switch(self) -> bool:
        return self._auto_switch

    @property
    def is_overridden(self) -> bool:
        return self._manual_override is not None

    @property
    def transition_history(self) -> list[PowerTransition]:
        return list(self._transition_history)

    def get_settings(self, profile: PowerProfile | None = None) -> dict[str, Any]:
        """Get the settings for a power profile."""
        target = profile or self.current_profile
        return dict(PROFILE_SETTINGS[target])

    def apply_transition(self, transition: PowerTransition) -> dict[str, Any]:
        """Apply a power profile transition.

        Returns the new settings dict for the target profile.
        """
        if self._manual_override is not None:
            logger.info(
                "Power transition %s → %s ignored (manual override to %s)",
                transition.from_profile.value,
                transition.to_profile.value,
                self._manual_override.value,
            )
            return self.get_settings()

        self._current_profile = transition.to_profile
        self._transition_history.append(transition)

        settings = self.get_settings()
        logger.info(
            "Power profile changed: %s → %s (battery: %.1f%%)",
            transition.from_profile.value,
            transition.to_profile.value,
            transition.battery_percent,
        )
        return settings

    def set_override(self, profile: PowerProfile) -> dict[str, Any]:
        """Manually override the power profile.

        Returns the new settings dict.
        """
        self._manual_override = profile
        logger.info("Power profile manually set to %s", profile.value)
        return self.get_settings()

    def clear_override(self) -> dict[str, Any]:
        """Clear the manual override, returning to auto mode.

        Returns the current auto-determined settings.
        """
        self._manual_override = None
        logger.info("Power profile override cleared, returning to auto mode")
        return self.get_settings()

    def update_from_state(self, state: PowerState) -> dict[str, Any] | None:
        """Update profile from a power state snapshot.

        Returns new settings if profile changed, None otherwise.
        """
        if not self._auto_switch:
            return None

        new_profile = state.profile
        if new_profile == self._current_profile:
            return None

        transition = PowerTransition(
            from_profile=self._current_profile,
            to_profile=new_profile,
            battery_percent=state.battery_percent,
        )
        return self.apply_transition(transition)
