"""Tests for SimulatedDevice and DeviceSimulator."""

from __future__ import annotations

import pytest

from cortex.iot.simulator import (
    DeviceSimulator,
    SimulatedDevice,
    create_demo_devices,
)
from cortex.iot.types import (
    DeviceCategory,
    DeviceCommand,
    DeviceSource,
    DeviceState,
)


class TestSimulatedDevice:
    def test_creation_defaults(self) -> None:
        device = SimulatedDevice("test_1", "Test Device")
        assert device.info.id == "test_1"
        assert device.info.friendly_name == "Test Device"
        assert device.info.category == DeviceCategory.LIGHT
        assert device.info.source == DeviceSource.SIMULATOR
        assert device.state.state == "off"

    def test_creation_custom(self) -> None:
        device = SimulatedDevice(
            "thermostat_1", "My Thermostat",
            category=DeviceCategory.CLIMATE,
            room="living_room",
            initial_state="heat",
        )
        assert device.info.category == DeviceCategory.CLIMATE
        assert device.info.room == "living_room"
        assert device.state.state == "heat"

    def test_turn_on(self) -> None:
        device = SimulatedDevice("test_1", "Test")
        assert device.state.state == "off"

        cmd = DeviceCommand(
            device_id="test_1", domain="light", service="turn_on",
        )
        new_state = device.handle_command(cmd)
        assert new_state.state == "on"
        assert device.state.state == "on"

    def test_turn_off(self) -> None:
        device = SimulatedDevice("test_1", "Test", initial_state="on")
        cmd = DeviceCommand(
            device_id="test_1", domain="light", service="turn_off",
        )
        new_state = device.handle_command(cmd)
        assert new_state.state == "off"

    def test_toggle_from_off(self) -> None:
        device = SimulatedDevice("test_1", "Test")
        cmd = DeviceCommand(
            device_id="test_1", domain="light", service="toggle",
        )
        new_state = device.handle_command(cmd)
        assert new_state.state == "on"

    def test_toggle_from_on(self) -> None:
        device = SimulatedDevice("test_1", "Test", initial_state="on")
        cmd = DeviceCommand(
            device_id="test_1", domain="light", service="toggle",
        )
        new_state = device.handle_command(cmd)
        assert new_state.state == "off"

    def test_unknown_service_preserves_state(self) -> None:
        device = SimulatedDevice("test_1", "Test", initial_state="on")
        cmd = DeviceCommand(
            device_id="test_1", domain="light", service="unknown_action",
        )
        new_state = device.handle_command(cmd)
        assert new_state.state == "on"

    def test_service_data_applied(self) -> None:
        device = SimulatedDevice("test_1", "Test")
        cmd = DeviceCommand(
            device_id="test_1",
            domain="light",
            service="turn_on",
            service_data={"brightness": 128},
        )
        new_state = device.handle_command(cmd)
        assert new_state.state == "on"
        assert new_state.attributes["brightness"] == 128

    def test_capabilities_light(self) -> None:
        device = SimulatedDevice("l", "L", category=DeviceCategory.LIGHT)
        caps = [c.name for c in device.info.capabilities]
        assert "state" in caps
        assert "brightness" in caps

    def test_capabilities_switch(self) -> None:
        device = SimulatedDevice("s", "S", category=DeviceCategory.SWITCH)
        caps = [c.name for c in device.info.capabilities]
        assert "state" in caps
        assert "brightness" not in caps

    def test_capabilities_climate(self) -> None:
        device = SimulatedDevice("c", "C", category=DeviceCategory.CLIMATE)
        caps = [c.name for c in device.info.capabilities]
        assert "target_temperature" in caps


class TestDeviceSimulator:
    @pytest.fixture()
    def simulator(self) -> DeviceSimulator:
        sim = DeviceSimulator()
        sim.add_device(SimulatedDevice("light_1", "Test Light", room="kitchen"))
        sim.add_device(
            SimulatedDevice(
                "switch_1", "Test Switch",
                category=DeviceCategory.SWITCH, room="kitchen",
            ),
        )
        return sim

    @pytest.mark.asyncio()
    async def test_connect_disconnect(self, simulator: DeviceSimulator) -> None:
        assert await simulator.health_check() is False
        await simulator.connect()
        assert await simulator.health_check() is True
        await simulator.disconnect()
        assert await simulator.health_check() is False

    @pytest.mark.asyncio()
    async def test_adapter_type(self, simulator: DeviceSimulator) -> None:
        assert simulator.adapter_type == "simulator"

    @pytest.mark.asyncio()
    async def test_device_count(self, simulator: DeviceSimulator) -> None:
        assert simulator.device_count == 2

    @pytest.mark.asyncio()
    async def test_get_devices(self, simulator: DeviceSimulator) -> None:
        devices = await simulator.get_devices()
        assert len(devices) == 2
        ids = [d.id for d in devices]
        assert "light_1" in ids
        assert "switch_1" in ids

    @pytest.mark.asyncio()
    async def test_get_state(self, simulator: DeviceSimulator) -> None:
        state = await simulator.get_state("light_1")
        assert state is not None
        assert state.state == "off"

    @pytest.mark.asyncio()
    async def test_get_state_unknown(self, simulator: DeviceSimulator) -> None:
        state = await simulator.get_state("nonexistent")
        assert state is None

    @pytest.mark.asyncio()
    async def test_send_command(self, simulator: DeviceSimulator) -> None:
        cmd = DeviceCommand(
            device_id="light_1", domain="light", service="turn_on",
        )
        result = await simulator.send_command(cmd)
        assert result is True

        state = await simulator.get_state("light_1")
        assert state is not None
        assert state.state == "on"

    @pytest.mark.asyncio()
    async def test_send_command_unknown_device(self, simulator: DeviceSimulator) -> None:
        cmd = DeviceCommand(
            device_id="nonexistent", domain="light", service="turn_on",
        )
        result = await simulator.send_command(cmd)
        assert result is False

    @pytest.mark.asyncio()
    async def test_state_callback(self, simulator: DeviceSimulator) -> None:
        states: list[DeviceState] = []
        simulator.subscribe_state(lambda did, s: states.append(s))

        cmd = DeviceCommand(
            device_id="light_1", domain="light", service="turn_on",
        )
        await simulator.send_command(cmd)
        assert len(states) == 1
        assert states[0].state == "on"


class TestCreateDemoDevices:
    def test_creates_devices(self) -> None:
        devices = create_demo_devices()
        assert len(devices) == 5

    def test_device_ids(self) -> None:
        devices = create_demo_devices()
        ids = [d.info.id for d in devices]
        assert "sim_kitchen_light" in ids
        assert "sim_living_room_light" in ids
        assert "sim_bedroom_lamp" in ids
        assert "sim_kitchen_plug" in ids
        assert "sim_thermostat" in ids

    def test_device_categories(self) -> None:
        devices = create_demo_devices()
        categories = {d.info.id: d.info.category for d in devices}
        assert categories["sim_kitchen_light"] == DeviceCategory.LIGHT
        assert categories["sim_kitchen_plug"] == DeviceCategory.SWITCH
        assert categories["sim_thermostat"] == DeviceCategory.CLIMATE

    def test_device_rooms(self) -> None:
        devices = create_demo_devices()
        rooms = {d.info.id: d.info.room for d in devices}
        assert rooms["sim_kitchen_light"] == "kitchen"
        assert rooms["sim_living_room_light"] == "living_room"
        assert rooms["sim_bedroom_lamp"] == "bedroom"

    def test_thermostat_initial_state(self) -> None:
        devices = create_demo_devices()
        thermostat = next(d for d in devices if d.info.id == "sim_thermostat")
        assert thermostat.state.state == "heat"
