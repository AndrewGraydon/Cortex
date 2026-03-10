"""Simulated device — virtual IoT devices for testing and demo.

Provides in-memory devices that accept commands and update state
without any hardware. Satisfies EC#1 without real MQTT/HA.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from cortex.iot.types import (
    DeviceCapability,
    DeviceCategory,
    DeviceCommand,
    DeviceInfo,
    DeviceSource,
    DeviceState,
)

logger = structlog.get_logger()


class SimulatedDevice:
    """A virtual device that accepts commands and tracks state."""

    def __init__(
        self,
        device_id: str,
        name: str,
        category: DeviceCategory = DeviceCategory.LIGHT,
        room: str = "",
        initial_state: str = "off",
    ) -> None:
        self.info = DeviceInfo(
            id=device_id,
            name=name,
            friendly_name=name,
            category=category,
            room=room,
            source=DeviceSource.SIMULATOR,
            capabilities=_default_capabilities(category),
        )
        self.state = DeviceState(
            device_id=device_id,
            state=initial_state,
        )

    def handle_command(self, command: DeviceCommand) -> DeviceState:
        """Process a command and update state."""
        attrs = dict(self.state.attributes)
        attrs.update(command.service_data)

        if command.service == "turn_on":
            new_state = "on"
        elif command.service == "turn_off":
            new_state = "off"
        elif command.service == "toggle":
            new_state = "off" if self.state.is_on else "on"
        else:
            new_state = self.state.state

        self.state = DeviceState(
            device_id=self.info.id,
            state=new_state,
            attributes=attrs,
        )
        return self.state


class DeviceSimulator:
    """Manages a collection of simulated devices.

    Implements IoTAdapter protocol.
    """

    def __init__(self) -> None:
        self._devices: dict[str, SimulatedDevice] = {}
        self._state_callbacks: list[Callable[[str, DeviceState], Any]] = []
        self._connected = False

    def add_device(self, device: SimulatedDevice) -> None:
        """Add a simulated device."""
        self._devices[device.info.id] = device

    async def connect(self) -> None:
        self._connected = True
        logger.info("DeviceSimulator connected", device_count=len(self._devices))

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("DeviceSimulator disconnected")

    async def health_check(self) -> bool:
        return self._connected

    async def send_command(self, command: DeviceCommand) -> bool:
        device = self._devices.get(command.device_id)
        if device is None:
            return False

        new_state = device.handle_command(command)
        for callback in self._state_callbacks:
            callback(command.device_id, new_state)

        logger.debug(
            "Simulated command",
            device_id=command.device_id,
            service=command.service,
            state=new_state.state,
        )
        return True

    async def get_devices(self) -> list[DeviceInfo]:
        return [d.info for d in self._devices.values()]

    async def get_state(self, device_id: str) -> DeviceState | None:
        device = self._devices.get(device_id)
        return device.state if device else None

    def subscribe_state(
        self,
        callback: Callable[[str, DeviceState], Any],
    ) -> None:
        self._state_callbacks.append(callback)

    @property
    def adapter_type(self) -> str:
        return "simulator"

    @property
    def device_count(self) -> int:
        return len(self._devices)


def create_demo_devices() -> list[SimulatedDevice]:
    """Create a set of demo devices for testing."""
    return [
        SimulatedDevice(
            "sim_kitchen_light", "Kitchen Light",
            DeviceCategory.LIGHT, room="kitchen",
        ),
        SimulatedDevice(
            "sim_living_room_light", "Living Room Light",
            DeviceCategory.LIGHT, room="living_room",
        ),
        SimulatedDevice(
            "sim_bedroom_lamp", "Bedroom Lamp",
            DeviceCategory.LIGHT, room="bedroom",
        ),
        SimulatedDevice(
            "sim_kitchen_plug", "Kitchen Plug",
            DeviceCategory.SWITCH, room="kitchen",
        ),
        SimulatedDevice(
            "sim_thermostat", "Thermostat",
            DeviceCategory.CLIMATE, room="living_room",
            initial_state="heat",
        ),
    ]


def _default_capabilities(category: DeviceCategory) -> list[DeviceCapability]:
    """Generate default capabilities for a device category."""
    if category == DeviceCategory.LIGHT:
        return [
            DeviceCapability(name="state", value_type="bool"),
            DeviceCapability(
                name="brightness", value_type="int", min_value=0, max_value=255,
            ),
        ]
    if category == DeviceCategory.SWITCH:
        return [DeviceCapability(name="state", value_type="bool")]
    if category == DeviceCategory.CLIMATE:
        return [
            DeviceCapability(name="state", value_type="bool"),
            DeviceCapability(
                name="target_temperature", value_type="float",
                min_value=16.0, max_value=30.0,
            ),
        ]
    return [DeviceCapability(name="state", value_type="bool")]
