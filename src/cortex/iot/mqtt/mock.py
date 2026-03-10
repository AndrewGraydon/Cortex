"""Mock MQTT client — in-memory pub/sub for testing."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import structlog

from cortex.iot.types import (
    DeviceCommand,
    DeviceInfo,
    DeviceState,
)

logger = structlog.get_logger()


class MockMqttClient:
    """In-memory MQTT client for testing.

    Simulates pub/sub without a real broker.
    Implements IoTAdapter protocol.
    """

    def __init__(self) -> None:
        self._connected = False
        self._devices: dict[str, DeviceInfo] = {}
        self._states: dict[str, DeviceState] = {}
        self._state_callbacks: list[Callable[[str, DeviceState], Any]] = []
        self._subscriptions: dict[str, Callable[[str, bytes], Any]] = {}
        self._published: list[tuple[str, bytes]] = []

    async def connect(self) -> None:
        self._connected = True
        logger.info("MockMqttClient connected")

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("MockMqttClient disconnected")

    async def health_check(self) -> bool:
        return self._connected

    async def send_command(self, command: DeviceCommand) -> bool:
        """Simulate sending a command — stores in published list."""
        if not self._connected:
            return False

        device = self._devices.get(command.device_id)
        topic = device.mqtt_topic if device else command.device_id

        payload = json.dumps({
            "service": command.service,
            **command.service_data,
        }).encode()
        self._published.append((f"{topic}/set", payload))

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
        return "mqtt"

    def register_device(self, device: DeviceInfo) -> None:
        """Register a device for testing."""
        self._devices[device.id] = device
        if device.id not in self._states:
            self._states[device.id] = DeviceState(device_id=device.id)

    def subscribe_topic(
        self,
        topic: str,
        callback: Callable[[str, bytes], Any],
    ) -> None:
        self._subscriptions[topic] = callback

    def simulate_message(self, topic: str, payload: bytes) -> None:
        """Simulate receiving a message on a topic."""
        callback = self._subscriptions.get(topic)
        if callback:
            callback(topic, payload)

    @property
    def published_messages(self) -> list[tuple[str, bytes]]:
        """Get list of published (topic, payload) tuples."""
        return list(self._published)

    @property
    def is_connected(self) -> bool:
        return self._connected
