"""IoT device data types — devices, states, commands, capabilities."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class DeviceCategory(enum.Enum):
    """High-level device categories."""

    LIGHT = "light"
    SWITCH = "switch"
    SENSOR = "sensor"
    COVER = "cover"
    CLIMATE = "climate"
    MEDIA_PLAYER = "media_player"
    LOCK = "lock"
    FAN = "fan"
    UNKNOWN = "unknown"


class DeviceSource(enum.Enum):
    """Where a device was discovered from."""

    MQTT = "mqtt"
    HOMEASSISTANT = "homeassistant"
    SIMULATOR = "simulator"
    MANUAL = "manual"


@dataclass(frozen=True)
class DeviceCapability:
    """A capability that a device supports."""

    name: str  # e.g. "brightness", "color_temp", "target_temperature"
    value_type: str = "bool"  # bool, int, float, string, enum
    min_value: float | None = None
    max_value: float | None = None
    enum_values: list[str] = field(default_factory=list)


@dataclass
class DeviceInfo:
    """Static device metadata."""

    id: str
    name: str
    friendly_name: str = ""
    category: DeviceCategory = DeviceCategory.UNKNOWN
    room: str = ""
    source: DeviceSource = DeviceSource.MANUAL
    capabilities: list[DeviceCapability] = field(default_factory=list)
    mqtt_topic: str = ""
    manufacturer: str = ""
    model: str = ""

    def __post_init__(self) -> None:
        if not self.friendly_name:
            self.friendly_name = self.name


@dataclass
class DeviceState:
    """Current state of a device."""

    device_id: str
    state: str = "unknown"  # on, off, unavailable, etc.
    attributes: dict[str, Any] = field(default_factory=dict)
    last_seen: datetime | None = None
    online: bool = True

    @property
    def is_on(self) -> bool:
        return self.state.lower() == "on"


@dataclass(frozen=True)
class DeviceCommand:
    """A command to send to a device."""

    device_id: str
    domain: str  # e.g. "light", "switch", "climate"
    service: str  # e.g. "turn_on", "turn_off", "set_temperature"
    service_data: dict[str, Any] = field(default_factory=dict)

    def format_display(self) -> str:
        """Format for TTS or text display."""
        action = self.service.replace("_", " ")
        return f"{action} {self.device_id}"
