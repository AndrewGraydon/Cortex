"""Power service — monitors battery state and publishes transitions.

Provides MockPowerService for testing and PiSugarPowerService for hardware.
"""

from __future__ import annotations

import logging
from typing import Protocol

from cortex.hal.power.types import (
    CRITICAL_THRESHOLD,
    LOW_BATTERY_THRESHOLD,
    PowerProfile,
    PowerState,
    PowerTransition,
)

logger = logging.getLogger(__name__)


class PowerService(Protocol):
    """Protocol for power monitoring services."""

    async def get_state(self) -> PowerState: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...


class MockPowerService:
    """Mock power service for testing.

    Allows setting battery state programmatically.
    """

    def __init__(self) -> None:
        self._state = PowerState()
        self._transitions: list[PowerTransition] = []
        self._running = False

    @property
    def transitions(self) -> list[PowerTransition]:
        return list(self._transitions)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def get_state(self) -> PowerState:
        return self._state

    def set_state(
        self,
        battery_percent: float = 100.0,
        is_charging: bool = True,
        voltage: float = 5.0,
    ) -> PowerTransition | None:
        """Set the mock battery state. Returns transition if profile changed."""
        old_profile = self._state.profile

        new_profile = _determine_profile(battery_percent, is_charging)

        self._state = PowerState(
            profile=new_profile,
            battery_percent=battery_percent,
            is_charging=is_charging,
            voltage=voltage,
        )

        if new_profile != old_profile:
            transition = PowerTransition(
                from_profile=old_profile,
                to_profile=new_profile,
                battery_percent=battery_percent,
            )
            self._transitions.append(transition)
            return transition

        return None


def _determine_profile(battery_percent: float, is_charging: bool) -> PowerProfile:
    """Determine the appropriate power profile based on battery state."""
    if is_charging:
        return PowerProfile.MAINS

    if battery_percent <= CRITICAL_THRESHOLD:
        return PowerProfile.CRITICAL
    if battery_percent <= LOW_BATTERY_THRESHOLD:
        return PowerProfile.LOW_BATTERY
    return PowerProfile.BATTERY
