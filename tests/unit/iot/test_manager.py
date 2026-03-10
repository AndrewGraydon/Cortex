"""Tests for IoT manager — lifecycle, command routing."""

from __future__ import annotations

from cortex.iot.manager import IoTManager
from cortex.iot.mqtt.mock import MockMqttClient
from cortex.iot.registry import DeviceRegistry
from cortex.iot.types import (
    DeviceCommand,
    DeviceInfo,
    DeviceSource,
    DeviceState,
)


class TestIoTManagerLifecycle:
    async def test_start_stop(self) -> None:
        manager = IoTManager()
        client = MockMqttClient()
        client.register_device(DeviceInfo(id="d1", name="Light", source=DeviceSource.MQTT))
        manager.register_adapter(client)

        await manager.start()
        assert manager.is_started is True
        assert manager.registry.device_count == 1

        await manager.stop()
        assert manager.is_started is False

    async def test_start_without_adapters(self) -> None:
        manager = IoTManager()
        await manager.start()
        assert manager.is_started is True
        await manager.stop()

    async def test_adapter_types(self) -> None:
        manager = IoTManager()
        client = MockMqttClient()
        manager.register_adapter(client)
        assert "mqtt" in manager.adapter_types


class TestIoTManagerCommands:
    async def test_send_command_to_mqtt(self) -> None:
        registry = DeviceRegistry()
        manager = IoTManager(registry=registry)
        client = MockMqttClient()
        client.register_device(
            DeviceInfo(id="d1", name="Light", source=DeviceSource.MQTT, mqtt_topic="z2m/light")
        )
        manager.register_adapter(client)
        await manager.start()

        cmd = DeviceCommand(device_id="d1", domain="light", service="turn_on")
        result = await manager.send_command(cmd)
        assert result is True

        messages = client.published_messages
        assert len(messages) == 1
        await manager.stop()

    async def test_send_command_unknown_device(self) -> None:
        manager = IoTManager()
        await manager.start()

        cmd = DeviceCommand(device_id="missing", domain="light", service="turn_on")
        result = await manager.send_command(cmd)
        assert result is False
        await manager.stop()

    async def test_send_command_no_matching_adapter(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()
        await registry.register_device(
            DeviceInfo(id="d1", name="HA Light", source=DeviceSource.HOMEASSISTANT)
        )

        manager = IoTManager(registry=registry)
        client = MockMqttClient()
        manager.register_adapter(client)
        await manager.start()

        cmd = DeviceCommand(device_id="d1", domain="light", service="turn_on")
        result = await manager.send_command(cmd)
        assert result is False
        await manager.stop()


class TestIoTManagerStateCallbacks:
    async def test_state_change_propagates(self) -> None:
        manager = IoTManager()
        client = MockMqttClient()
        client.register_device(DeviceInfo(id="d1", name="Light", source=DeviceSource.MQTT))
        manager.register_adapter(client)
        await manager.start()

        received: list[tuple[str, DeviceState]] = []
        manager.subscribe_state(lambda did, s: received.append((did, s)))

        cmd = DeviceCommand(device_id="d1", domain="light", service="turn_on")
        await client.send_command(cmd)

        assert len(received) == 1
        assert received[0][0] == "d1"
        assert received[0][1].state == "on"
        await manager.stop()


class TestIoTManagerHealthCheck:
    async def test_health_check(self) -> None:
        manager = IoTManager()
        client = MockMqttClient()
        manager.register_adapter(client)
        await manager.start()

        health = await manager.health_check()
        assert "mqtt" in health
        assert health["mqtt"] is True
        await manager.stop()

    async def test_health_check_disconnected(self) -> None:
        manager = IoTManager()
        client = MockMqttClient()
        manager.register_adapter(client)

        # Not started — client not connected
        health = await manager.health_check()
        assert health["mqtt"] is False
