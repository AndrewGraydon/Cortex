"""Tests for Home Assistant client and mock."""

from __future__ import annotations

import pytest

from cortex.iot.homeassistant.client import (
    HomeAssistantClient,
    _entity_to_device_info,
    _entity_to_device_state,
)
from cortex.iot.homeassistant.mock import MockHomeAssistantClient
from cortex.iot.types import (
    DeviceCategory,
    DeviceCommand,
    DeviceInfo,
    DeviceSource,
    DeviceState,
)

# --- Entity parsing helpers ---


class TestEntityToDeviceInfo:
    def test_light_entity(self) -> None:
        entity = {
            "entity_id": "light.kitchen",
            "state": "on",
            "attributes": {"friendly_name": "Kitchen Light", "brightness": 200},
        }
        info = _entity_to_device_info(entity)
        assert info is not None
        assert info.id == "light.kitchen"
        assert info.friendly_name == "Kitchen Light"
        assert info.category == DeviceCategory.LIGHT
        assert info.source == DeviceSource.HOMEASSISTANT

    def test_switch_entity(self) -> None:
        entity = {
            "entity_id": "switch.coffee_maker",
            "state": "off",
            "attributes": {"friendly_name": "Coffee Maker"},
        }
        info = _entity_to_device_info(entity)
        assert info is not None
        assert info.category == DeviceCategory.SWITCH

    def test_sensor_entity(self) -> None:
        entity = {
            "entity_id": "sensor.temperature",
            "state": "22.5",
            "attributes": {"friendly_name": "Temperature Sensor"},
        }
        info = _entity_to_device_info(entity)
        assert info is not None
        assert info.category == DeviceCategory.SENSOR

    def test_binary_sensor_entity(self) -> None:
        entity = {
            "entity_id": "binary_sensor.door",
            "state": "off",
            "attributes": {"friendly_name": "Front Door"},
        }
        info = _entity_to_device_info(entity)
        assert info is not None
        assert info.category == DeviceCategory.SENSOR

    def test_climate_entity(self) -> None:
        entity = {
            "entity_id": "climate.thermostat",
            "state": "heat",
            "attributes": {"friendly_name": "Thermostat"},
        }
        info = _entity_to_device_info(entity)
        assert info is not None
        assert info.category == DeviceCategory.CLIMATE

    def test_unknown_domain(self) -> None:
        entity = {
            "entity_id": "automation.morning",
            "state": "on",
            "attributes": {"friendly_name": "Morning Routine"},
        }
        info = _entity_to_device_info(entity)
        assert info is not None
        assert info.category == DeviceCategory.UNKNOWN

    def test_empty_entity_id(self) -> None:
        entity = {"entity_id": "", "state": "on", "attributes": {}}
        assert _entity_to_device_info(entity) is None

    def test_missing_entity_id(self) -> None:
        entity = {"state": "on", "attributes": {}}
        assert _entity_to_device_info(entity) is None

    def test_no_friendly_name_uses_entity_id(self) -> None:
        entity = {"entity_id": "light.test", "state": "on", "attributes": {}}
        info = _entity_to_device_info(entity)
        assert info is not None
        assert info.friendly_name == "light.test"


class TestEntityToDeviceState:
    def test_basic_state(self) -> None:
        entity = {
            "entity_id": "light.kitchen",
            "state": "on",
            "attributes": {"brightness": 200},
        }
        state = _entity_to_device_state(entity)
        assert state.device_id == "light.kitchen"
        assert state.state == "on"
        assert state.is_on is True
        assert state.attributes["brightness"] == 200
        assert state.online is True

    def test_unavailable_state(self) -> None:
        entity = {
            "entity_id": "light.kitchen",
            "state": "unavailable",
            "attributes": {},
        }
        state = _entity_to_device_state(entity)
        assert state.online is False

    def test_missing_fields(self) -> None:
        entity = {}
        state = _entity_to_device_state(entity)
        assert state.device_id == ""
        assert state.state == "unknown"


# --- HomeAssistantClient init ---


class TestHomeAssistantClientInit:
    def test_creation(self) -> None:
        client = HomeAssistantClient("http://ha.local:8123")
        assert client.adapter_type == "homeassistant"

    def test_url_trailing_slash_stripped(self) -> None:
        client = HomeAssistantClient("http://ha.local:8123/")
        assert client._url == "http://ha.local:8123"

    def test_custom_token_env(self) -> None:
        client = HomeAssistantClient("http://ha.local:8123", token_env="MY_TOKEN")
        assert client._token_env == "MY_TOKEN"


# --- MockHomeAssistantClient ---


class TestMockHomeAssistantClient:
    @pytest.fixture()
    def mock_client(self) -> MockHomeAssistantClient:
        return MockHomeAssistantClient()

    @pytest.mark.asyncio()
    async def test_connect_disconnect(self, mock_client: MockHomeAssistantClient) -> None:
        assert await mock_client.health_check() is False
        await mock_client.connect()
        assert await mock_client.health_check() is True
        await mock_client.disconnect()
        assert await mock_client.health_check() is False

    @pytest.mark.asyncio()
    async def test_register_and_get_devices(
        self, mock_client: MockHomeAssistantClient,
    ) -> None:
        device = DeviceInfo(
            id="light.test",
            name="light.test",
            friendly_name="Test Light",
            category=DeviceCategory.LIGHT,
            source=DeviceSource.HOMEASSISTANT,
        )
        mock_client.register_device(device)

        devices = await mock_client.get_devices()
        assert len(devices) == 1
        assert devices[0].id == "light.test"

    @pytest.mark.asyncio()
    async def test_get_state(self, mock_client: MockHomeAssistantClient) -> None:
        device = DeviceInfo(
            id="light.test",
            name="light.test",
            friendly_name="Test Light",
            category=DeviceCategory.LIGHT,
            source=DeviceSource.HOMEASSISTANT,
        )
        mock_client.register_device(device)

        state = await mock_client.get_state("light.test")
        assert state is not None
        assert state.device_id == "light.test"

    @pytest.mark.asyncio()
    async def test_get_state_unknown(self, mock_client: MockHomeAssistantClient) -> None:
        state = await mock_client.get_state("nonexistent")
        assert state is None

    @pytest.mark.asyncio()
    async def test_send_command_not_connected(
        self, mock_client: MockHomeAssistantClient,
    ) -> None:
        cmd = DeviceCommand(
            device_id="light.test", domain="light", service="turn_on",
        )
        result = await mock_client.send_command(cmd)
        assert result is False

    @pytest.mark.asyncio()
    async def test_send_command_turn_on(
        self, mock_client: MockHomeAssistantClient,
    ) -> None:
        await mock_client.connect()
        device = DeviceInfo(
            id="light.test",
            name="light.test",
            friendly_name="Test Light",
            category=DeviceCategory.LIGHT,
            source=DeviceSource.HOMEASSISTANT,
        )
        mock_client.register_device(device)

        cmd = DeviceCommand(
            device_id="light.test", domain="light", service="turn_on",
        )
        result = await mock_client.send_command(cmd)
        assert result is True

        state = await mock_client.get_state("light.test")
        assert state is not None
        assert state.state == "on"

    @pytest.mark.asyncio()
    async def test_send_command_turn_off(
        self, mock_client: MockHomeAssistantClient,
    ) -> None:
        await mock_client.connect()
        device = DeviceInfo(
            id="light.test",
            name="light.test",
            friendly_name="Test Light",
            category=DeviceCategory.LIGHT,
            source=DeviceSource.HOMEASSISTANT,
        )
        mock_client.register_device(device)

        cmd = DeviceCommand(
            device_id="light.test", domain="light", service="turn_off",
        )
        result = await mock_client.send_command(cmd)
        assert result is True

        state = await mock_client.get_state("light.test")
        assert state is not None
        assert state.state == "off"

    @pytest.mark.asyncio()
    async def test_service_calls_tracked(
        self, mock_client: MockHomeAssistantClient,
    ) -> None:
        await mock_client.connect()
        cmd = DeviceCommand(
            device_id="light.test", domain="light", service="turn_on",
        )
        await mock_client.send_command(cmd)
        assert len(mock_client.service_calls) == 1
        assert mock_client.service_calls[0].service == "turn_on"

    @pytest.mark.asyncio()
    async def test_state_callback(self, mock_client: MockHomeAssistantClient) -> None:
        await mock_client.connect()
        device = DeviceInfo(
            id="light.test",
            name="light.test",
            friendly_name="Test Light",
            category=DeviceCategory.LIGHT,
            source=DeviceSource.HOMEASSISTANT,
        )
        mock_client.register_device(device)

        states: list[DeviceState] = []
        mock_client.subscribe_state(lambda did, s: states.append(s))

        cmd = DeviceCommand(
            device_id="light.test", domain="light", service="turn_on",
        )
        await mock_client.send_command(cmd)
        assert len(states) == 1
        assert states[0].state == "on"

    @pytest.mark.asyncio()
    async def test_adapter_type(self, mock_client: MockHomeAssistantClient) -> None:
        assert mock_client.adapter_type == "homeassistant"
