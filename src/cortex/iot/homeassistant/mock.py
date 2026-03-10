"""Mock Home Assistant client — in-memory for testing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from cortex.iot.types import (
    DeviceCommand,
    DeviceInfo,
    DeviceState,
)

logger = structlog.get_logger()


class MockHomeAssistantClient:
    """In-memory HA client for testing.

    Simulates HA REST API without a real server.
    Implements IoTAdapter protocol.
    """

    def __init__(self) -> None:
        self._connected = False
        self._devices: dict[str, DeviceInfo] = {}
        self._states: dict[str, DeviceState] = {}
        self._state_callbacks: list[Callable[[str, DeviceState], Any]] = []
        self._service_calls: list[DeviceCommand] = []

    async def connect(self) -> None:
        self._connected = True
        logger.info("MockHomeAssistantClient connected")

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("MockHomeAssistantClient disconnected")

    async def health_check(self) -> bool:
        return self._connected

    async def send_command(self, command: DeviceCommand) -> bool:
        if not self._connected:
            return False
        self._service_calls.append(command)

        # Simulate state change for simple commands
        if command.service in ("turn_on", "turn_off"):
            new_state = "on" if command.service == "turn_on" else "off"
            state = DeviceState(
                device_id=command.device_id,
                state=new_state,
                attributes=command.service_data,
            )
            self._states[command.device_id] = state
            for callback in self._state_callbacks:
                callback(command.device_id, state)
        return True

    async def get_devices(self) -> list[DeviceInfo]:
        return list(self._devices.values())

    async def get_state(self, device_id: str) -> DeviceState | None:
        return self._states.get(device_id)

    def subscribe_state(
        self,
        callback: Callable[[str, DeviceState], Any],
    ) -> None:
        self._state_callbacks.append(callback)

    @property
    def adapter_type(self) -> str:
        return "homeassistant"

    def register_device(self, device: DeviceInfo) -> None:
        """Register a device for testing."""
        self._devices[device.id] = device
        if device.id not in self._states:
            self._states[device.id] = DeviceState(device_id=device.id)

    @property
    def service_calls(self) -> list[DeviceCommand]:
        """List of service calls made (for testing)."""
        return list(self._service_calls)
