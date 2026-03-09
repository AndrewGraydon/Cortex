"""Power types — profiles, state, and transitions."""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field


class PowerProfile(enum.Enum):
    """Power profile modes."""

    MAINS = "mains"
    BATTERY = "battery"
    LOW_BATTERY = "low_battery"
    CRITICAL = "critical"


@dataclass
class PowerState:
    """Current power state snapshot."""

    profile: PowerProfile = PowerProfile.MAINS
    battery_percent: float = 100.0
    is_charging: bool = True
    voltage: float = 5.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class PowerTransition:
    """A power profile transition event."""

    from_profile: PowerProfile
    to_profile: PowerProfile
    battery_percent: float
    timestamp: float = field(default_factory=time.time)


# Profile thresholds (battery percent)
BATTERY_THRESHOLD = 100.0  # Below this when not charging → BATTERY
LOW_BATTERY_THRESHOLD = 20.0  # Below this → LOW_BATTERY
CRITICAL_THRESHOLD = 5.0  # Below this → CRITICAL
