"""Tests for MQTT auto-discovery — HA + Zigbee2MQTT parsing."""

from __future__ import annotations

import json

from cortex.iot.mqtt.discovery import (
    parse_ha_discovery,
    parse_z2m_devices,
)
from cortex.iot.types import DeviceCategory, DeviceSource

# --- HA MQTT Discovery ---


class TestHADiscovery:
    def test_parse_light(self) -> None:
        topic = "homeassistant/light/kitchen_bulb/config"
        payload = json.dumps({
            "name": "Kitchen Bulb",
            "unique_id": "kitchen_bulb_001",
            "command_topic": "zigbee2mqtt/kitchen_bulb/set",
            "state_topic": "zigbee2mqtt/kitchen_bulb",
            "brightness_command_topic": "zigbee2mqtt/kitchen_bulb/set",
            "brightness_scale": 254,
            "device": {
                "manufacturer": "Philips",
                "model": "Hue White",
            },
        }).encode()

        device = parse_ha_discovery(topic, payload)
        assert device is not None
        assert device.id == "kitchen_bulb_001"
        assert device.name == "Kitchen Bulb"
        assert device.category == DeviceCategory.LIGHT
        assert device.source == DeviceSource.MQTT
        assert device.manufacturer == "Philips"
        assert len(device.capabilities) >= 2  # state + brightness

    def test_parse_switch(self) -> None:
        topic = "homeassistant/switch/plug_1/config"
        payload = json.dumps({
            "name": "Smart Plug",
            "unique_id": "plug_001",
            "command_topic": "zigbee2mqtt/plug_1/set",
        }).encode()

        device = parse_ha_discovery(topic, payload)
        assert device is not None
        assert device.category == DeviceCategory.SWITCH
        assert len(device.capabilities) == 1

    def test_parse_sensor(self) -> None:
        topic = "homeassistant/sensor/temp_1/config"
        payload = json.dumps({
            "name": "Temperature",
            "unique_id": "temp_001",
            "state_topic": "zigbee2mqtt/temp_sensor",
            "unit_of_measurement": "°C",
        }).encode()

        device = parse_ha_discovery(topic, payload)
        assert device is not None
        assert device.category == DeviceCategory.SENSOR

    def test_parse_climate(self) -> None:
        topic = "homeassistant/climate/thermostat/config"
        payload = json.dumps({
            "name": "Thermostat",
            "unique_id": "thermo_001",
            "command_topic": "zigbee2mqtt/thermostat/set",
            "modes": ["heat", "cool", "auto", "off"],
        }).encode()

        device = parse_ha_discovery(topic, payload)
        assert device is not None
        assert device.category == DeviceCategory.CLIMATE
        mode_cap = [c for c in device.capabilities if c.name == "mode"]
        assert len(mode_cap) == 1
        assert "heat" in mode_cap[0].enum_values

    def test_parse_unknown_component(self) -> None:
        topic = "homeassistant/vacuum/roomba/config"
        payload = json.dumps({
            "name": "Roomba",
            "unique_id": "roomba_001",
        }).encode()

        device = parse_ha_discovery(topic, payload)
        assert device is not None
        assert device.category == DeviceCategory.UNKNOWN

    def test_invalid_topic(self) -> None:
        device = parse_ha_discovery("invalid/topic", b"{}")
        assert device is None

    def test_invalid_json(self) -> None:
        topic = "homeassistant/light/test/config"
        device = parse_ha_discovery(topic, b"not json")
        assert device is None

    def test_empty_payload(self) -> None:
        topic = "homeassistant/light/test/config"
        device = parse_ha_discovery(topic, b"null")
        assert device is None

    def test_node_id_as_fallback(self) -> None:
        topic = "homeassistant/light/my_light/config"
        payload = json.dumps({"name": "My Light"}).encode()

        device = parse_ha_discovery(topic, payload)
        assert device is not None
        assert device.id == "my_light"  # Falls back to node_id


# --- Zigbee2MQTT Discovery ---


class TestZ2MDiscovery:
    def test_parse_devices(self) -> None:
        payload = json.dumps([
            {
                "ieee_address": "0x001122334455",
                "friendly_name": "Kitchen Light",
                "definition": {
                    "description": "Smart LED bulb",
                    "vendor": "IKEA",
                    "model": "TRADFRI",
                },
            },
            {
                "ieee_address": "0x556677889900",
                "friendly_name": "Motion Sensor",
                "definition": {
                    "description": "Temperature and humidity sensor",
                    "vendor": "Aqara",
                    "model": "WSDCGQ11LM",
                },
            },
        ]).encode()

        devices = parse_z2m_devices(payload)
        assert len(devices) == 2

        light = devices[0]
        assert light.name == "Kitchen Light"
        assert light.category == DeviceCategory.LIGHT
        assert light.manufacturer == "IKEA"
        assert light.mqtt_topic == "zigbee2mqtt/Kitchen Light"

        sensor = devices[1]
        assert sensor.category == DeviceCategory.SENSOR

    def test_parse_empty(self) -> None:
        devices = parse_z2m_devices(b"[]")
        assert devices == []

    def test_parse_invalid_json(self) -> None:
        devices = parse_z2m_devices(b"not json")
        assert devices == []

    def test_parse_non_array(self) -> None:
        devices = parse_z2m_devices(b'{"key": "value"}')
        assert devices == []

    def test_unknown_category(self) -> None:
        payload = json.dumps([
            {
                "ieee_address": "0xAA",
                "friendly_name": "Mystery Device",
                "definition": {
                    "description": "Some unknown gadget",
                    "vendor": "Unknown",
                },
            },
        ]).encode()

        devices = parse_z2m_devices(payload)
        assert len(devices) == 1
        assert devices[0].category == DeviceCategory.UNKNOWN

    def test_switch_category(self) -> None:
        payload = json.dumps([
            {
                "ieee_address": "0xBB",
                "friendly_name": "Power Plug",
                "definition": {
                    "description": "Smart plug outlet",
                    "vendor": "Sonoff",
                },
            },
        ]).encode()

        devices = parse_z2m_devices(payload)
        assert devices[0].category == DeviceCategory.SWITCH

    def test_no_definition(self) -> None:
        payload = json.dumps([
            {
                "ieee_address": "0xCC",
                "friendly_name": "Bare Device",
            },
        ]).encode()

        devices = parse_z2m_devices(payload)
        assert len(devices) == 1
        assert devices[0].category == DeviceCategory.UNKNOWN
