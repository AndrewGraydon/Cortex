"""Tests for mock MQTT client."""

from __future__ import annotations

import json

from cortex.iot.mqtt.mock import MockMqttClient
from cortex.iot.types import (
    DeviceCommand,
    DeviceInfo,
    DeviceSource,
    DeviceState,
)


class TestMockMqttClientLifecycle:
    async def test_connect(self) -> None:
        client = MockMqttClient()
        await client.connect()
        assert client.is_connected is True

    async def test_disconnect(self) -> None:
        client = MockMqttClient()
        await client.connect()
        await client.disconnect()
        assert client.is_connected is False

    async def test_health_check_connected(self) -> None:
        client = MockMqttClient()
        await client.connect()
        assert await client.health_check() is True

    async def test_health_check_disconnected(self) -> None:
        client = MockMqttClient()
        assert await client.health_check() is False

    def test_adapter_type(self) -> None:
        client = MockMqttClient()
        assert client.adapter_type == "mqtt"


class TestMockMqttClientCommands:
    async def test_send_command(self) -> None:
        client = MockMqttClient()
        await client.connect()

        device = DeviceInfo(
            id="light1",
            name="Kitchen Light",
            mqtt_topic="zigbee2mqtt/kitchen_light",
            source=DeviceSource.MQTT,
        )
        client.register_device(device)

        cmd = DeviceCommand(
            device_id="light1",
            domain="light",
            service="turn_on",
            service_data={"brightness": 200},
        )
        result = await client.send_command(cmd)
        assert result is True

        messages = client.published_messages
        assert len(messages) == 1
        topic, payload = messages[0]
        assert topic == "zigbee2mqtt/kitchen_light/set"
        data = json.loads(payload)
        assert data["service"] == "turn_on"
        assert data["brightness"] == 200

    async def test_send_command_disconnected(self) -> None:
        client = MockMqttClient()
        cmd = DeviceCommand(device_id="d1", domain="light", service="turn_on")
        result = await client.send_command(cmd)
        assert result is False

    async def test_command_updates_state(self) -> None:
        client = MockMqttClient()
        await client.connect()
        client.register_device(DeviceInfo(id="d1", name="Light"))

        cmd = DeviceCommand(device_id="d1", domain="light", service="turn_on")
        await client.send_command(cmd)

        state = await client.get_state("d1")
        assert state is not None
        assert state.state == "on"

    async def test_turn_off_command(self) -> None:
        client = MockMqttClient()
        await client.connect()
        client.register_device(DeviceInfo(id="d1", name="Light"))

        await client.send_command(
            DeviceCommand(device_id="d1", domain="light", service="turn_on")
        )
        await client.send_command(
            DeviceCommand(device_id="d1", domain="light", service="turn_off")
        )

        state = await client.get_state("d1")
        assert state is not None
        assert state.state == "off"


class TestMockMqttClientSubscriptions:
    async def test_subscribe_state_callback(self) -> None:
        client = MockMqttClient()
        await client.connect()
        client.register_device(DeviceInfo(id="d1", name="Light"))

        received: list[tuple[str, DeviceState]] = []
        client.subscribe_state(lambda did, s: received.append((did, s)))

        cmd = DeviceCommand(device_id="d1", domain="light", service="turn_on")
        await client.send_command(cmd)

        assert len(received) == 1
        assert received[0][0] == "d1"
        assert received[0][1].state == "on"

    def test_subscribe_topic(self) -> None:
        client = MockMqttClient()
        received: list[tuple[str, bytes]] = []
        client.subscribe_topic("test/topic", lambda t, p: received.append((t, p)))
        client.simulate_message("test/topic", b'{"temp": 22}')

        assert len(received) == 1
        assert received[0][0] == "test/topic"

    def test_unsubscribed_topic_ignored(self) -> None:
        client = MockMqttClient()
        received: list[tuple[str, bytes]] = []
        client.subscribe_topic("my/topic", lambda t, p: received.append((t, p)))
        client.simulate_message("other/topic", b"data")

        assert len(received) == 0


class TestMockMqttClientDevices:
    async def test_get_devices(self) -> None:
        client = MockMqttClient()
        client.register_device(DeviceInfo(id="d1", name="Light 1"))
        client.register_device(DeviceInfo(id="d2", name="Light 2"))

        devices = await client.get_devices()
        assert len(devices) == 2

    async def test_register_creates_default_state(self) -> None:
        client = MockMqttClient()
        client.register_device(DeviceInfo(id="d1", name="Light"))

        state = await client.get_state("d1")
        assert state is not None
        assert state.device_id == "d1"
