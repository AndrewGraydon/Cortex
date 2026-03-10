"""MQTT client — paho-mqtt v2 async wrapper with auto-reconnect.

Wraps paho-mqtt v2 to provide an async interface for publishing,
subscribing, and receiving MQTT messages. Implements IoTAdapter protocol.
"""

from __future__ import annotations

import asyncio
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


class MqttClient:
    """Async MQTT client wrapping paho-mqtt v2.

    Implements IoTAdapter protocol for IoT device communication.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1883,
        username: str = "",
        password: str = "",
        client_id: str = "cortex",
        reconnect_max_delay: int = 60,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._client_id = client_id
        self._reconnect_max_delay = reconnect_max_delay
        self._client: Any = None
        self._connected = False
        self._state_callbacks: list[Callable[[str, DeviceState], Any]] = []
        self._devices: dict[str, DeviceInfo] = {}
        self._subscriptions: dict[str, Callable[[str, bytes], Any]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self) -> None:
        """Connect to the MQTT broker."""
        try:
            import paho.mqtt.client as mqtt  # noqa: PLC0415

            self._loop = asyncio.get_event_loop()
            self._client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,  # type: ignore[attr-defined]
                client_id=self._client_id,
            )
            if self._username:
                self._client.username_pw_set(self._username, self._password)

            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_message = self._on_message
            self._client.reconnect_delay_set(min_delay=1, max_delay=self._reconnect_max_delay)

            self._client.connect_async(self._host, self._port)
            self._client.loop_start()
            self._connected = True
            logger.info("MQTT connecting", host=self._host, port=self._port)
        except Exception:
            self._connected = False
            logger.exception("MQTT connection failed")
            raise

    async def disconnect(self) -> None:
        """Disconnect from the MQTT broker."""
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
        self._connected = False
        logger.info("MQTT disconnected")

    async def health_check(self) -> bool:
        """Check if connected to broker."""
        return self._connected and self._client is not None

    async def send_command(self, command: DeviceCommand) -> bool:
        """Publish a command to the device's MQTT topic."""
        if self._client is None or not self._connected:
            return False

        device = self._devices.get(command.device_id)
        topic = device.mqtt_topic if device else command.device_id

        payload = json.dumps({
            "service": command.service,
            **command.service_data,
        })

        try:
            result = self._client.publish(f"{topic}/set", payload)
            return bool(result.rc == 0)
        except Exception:
            logger.exception("MQTT publish failed", topic=topic)
            return False

    async def get_devices(self) -> list[DeviceInfo]:
        """Return discovered devices."""
        return list(self._devices.values())

    async def get_state(self, device_id: str) -> DeviceState | None:
        """Get cached state for a device (not direct query)."""
        return None  # State comes from subscriptions

    def subscribe_state(
        self,
        callback: Callable[[str, DeviceState], Any],
    ) -> None:
        """Subscribe to state change notifications."""
        self._state_callbacks.append(callback)

    @property
    def adapter_type(self) -> str:
        return "mqtt"

    def subscribe_topic(
        self,
        topic: str,
        callback: Callable[[str, bytes], Any],
    ) -> None:
        """Subscribe to a specific MQTT topic."""
        self._subscriptions[topic] = callback
        if self._client is not None and self._connected:
            self._client.subscribe(topic)

    def publish(self, topic: str, payload: str | bytes, retain: bool = False) -> bool:
        """Publish a message to an MQTT topic."""
        if self._client is None or not self._connected:
            return False
        try:
            result = self._client.publish(topic, payload, retain=retain)
            return bool(result.rc == 0)
        except Exception:
            logger.exception("MQTT publish failed", topic=topic)
            return False

    def register_device(self, device: DeviceInfo) -> None:
        """Register a discovered device."""
        self._devices[device.id] = device

    def _on_connect(
        self, client: Any, userdata: Any, flags: Any, rc: Any,
        properties: Any = None,
    ) -> None:
        """Paho callback: connected to broker."""
        logger.info("MQTT connected", host=self._host)
        self._connected = True
        for topic in self._subscriptions:
            client.subscribe(topic)

    def _on_disconnect(
        self, client: Any, userdata: Any, flags: Any, rc: Any,
        properties: Any = None,
    ) -> None:
        """Paho callback: disconnected from broker."""
        logger.warning("MQTT disconnected", rc=rc)
        self._connected = False

    def _on_message(self, client: Any, userdata: Any, msg: Any) -> None:
        """Paho callback: message received."""
        topic = msg.topic
        payload = msg.payload

        callback = self._subscriptions.get(topic)
        if callback is not None:
            try:
                callback(topic, payload)
            except Exception:
                logger.exception("MQTT message callback error", topic=topic)

    @property
    def is_connected(self) -> bool:
        return self._connected
