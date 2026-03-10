"""Tests for IoT device types."""

from __future__ import annotations

from cortex.iot.types import (
    DeviceCapability,
    DeviceCategory,
    DeviceCommand,
    DeviceInfo,
    DeviceSource,
    DeviceState,
)


class TestDeviceCategory:
    def test_values(self) -> None:
        assert DeviceCategory.LIGHT.value == "light"
        assert DeviceCategory.SWITCH.value == "switch"
        assert DeviceCategory.SENSOR.value == "sensor"
        assert DeviceCategory.CLIMATE.value == "climate"
        assert DeviceCategory.UNKNOWN.value == "unknown"


class TestDeviceSource:
    def test_values(self) -> None:
        assert DeviceSource.MQTT.value == "mqtt"
        assert DeviceSource.HOMEASSISTANT.value == "homeassistant"
        assert DeviceSource.SIMULATOR.value == "simulator"


class TestDeviceInfo:
    def test_defaults(self) -> None:
        info = DeviceInfo(id="d1", name="Test Light")
        assert info.friendly_name == "Test Light"  # auto-set from name
        assert info.category == DeviceCategory.UNKNOWN
        assert info.room == ""
        assert info.source == DeviceSource.MANUAL
        assert info.capabilities == []

    def test_custom_friendly_name(self) -> None:
        info = DeviceInfo(id="d1", name="light_1", friendly_name="Kitchen Light")
        assert info.friendly_name == "Kitchen Light"

    def test_auto_friendly_name(self) -> None:
        info = DeviceInfo(id="d1", name="test_device")
        assert info.friendly_name == "test_device"

    def test_with_capabilities(self) -> None:
        caps = [
            DeviceCapability(name="brightness", value_type="int", min_value=0, max_value=255),
            DeviceCapability(name="state", value_type="bool"),
        ]
        info = DeviceInfo(id="d1", name="Bulb", capabilities=caps)
        assert len(info.capabilities) == 2
        assert info.capabilities[0].name == "brightness"
        assert info.capabilities[0].max_value == 255


class TestDeviceState:
    def test_defaults(self) -> None:
        state = DeviceState(device_id="d1")
        assert state.state == "unknown"
        assert state.attributes == {}
        assert state.online is True
        assert state.is_on is False

    def test_is_on(self) -> None:
        state = DeviceState(device_id="d1", state="on")
        assert state.is_on is True

    def test_is_off(self) -> None:
        state = DeviceState(device_id="d1", state="off")
        assert state.is_on is False

    def test_case_insensitive(self) -> None:
        state = DeviceState(device_id="d1", state="ON")
        assert state.is_on is True

    def test_attributes(self) -> None:
        state = DeviceState(
            device_id="d1",
            state="on",
            attributes={"brightness": 200, "color_temp": 350},
        )
        assert state.attributes["brightness"] == 200


class TestDeviceCommand:
    def test_basic(self) -> None:
        cmd = DeviceCommand(
            device_id="d1",
            domain="light",
            service="turn_on",
        )
        assert cmd.device_id == "d1"
        assert cmd.service == "turn_on"
        assert cmd.service_data == {}

    def test_with_service_data(self) -> None:
        cmd = DeviceCommand(
            device_id="d1",
            domain="light",
            service="turn_on",
            service_data={"brightness": 200},
        )
        assert cmd.service_data["brightness"] == 200

    def test_format_display(self) -> None:
        cmd = DeviceCommand(device_id="kitchen_light", domain="light", service="turn_on")
        display = cmd.format_display()
        assert "turn on" in display
        assert "kitchen_light" in display


class TestDeviceCapability:
    def test_basic(self) -> None:
        cap = DeviceCapability(name="brightness", value_type="int")
        assert cap.name == "brightness"
        assert cap.min_value is None

    def test_with_range(self) -> None:
        cap = DeviceCapability(
            name="temperature", value_type="float", min_value=16.0, max_value=30.0,
        )
        assert cap.min_value == 16.0
        assert cap.max_value == 30.0

    def test_enum(self) -> None:
        cap = DeviceCapability(name="mode", value_type="enum", enum_values=["heat", "cool", "auto"])
        assert len(cap.enum_values) == 3
