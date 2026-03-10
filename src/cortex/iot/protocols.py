"""IoT adapter protocol — interface for MQTT, Home Assistant, etc."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from cortex.iot.types import DeviceCommand, DeviceInfo, DeviceState


class IoTAdapter(Protocol):
    """Protocol for IoT device communication backends."""

    async def connect(self) -> None:
        """Connect to the IoT backend."""
        ...

    async def disconnect(self) -> None:
        """Disconnect from the IoT backend."""
        ...

    async def health_check(self) -> bool:
        """Check if the backend is reachable."""
        ...

    async def send_command(self, command: DeviceCommand) -> bool:
        """Send a command to a device. Returns True on success."""
        ...

    async def get_devices(self) -> list[DeviceInfo]:
        """Get all known devices from this adapter."""
        ...

    async def get_state(self, device_id: str) -> DeviceState | None:
        """Get current state of a device."""
        ...

    def subscribe_state(
        self,
        callback: Callable[[str, DeviceState], Any],
    ) -> None:
        """Subscribe to state change notifications."""
        ...

    @property
    def adapter_type(self) -> str:
        """Adapter type identifier: 'mqtt', 'homeassistant', 'simulator'."""
        ...
