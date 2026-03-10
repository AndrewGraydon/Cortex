"""Tests for device control, query, and list tools."""

from __future__ import annotations

import pytest

from cortex.agent.tools.builtin.device_control import (
    DeviceControlTool,
    DeviceListTool,
    DeviceQueryTool,
    get_iot_backend,
    set_iot_backend,
)
from cortex.iot.registry import DeviceRegistry
from cortex.iot.resolver import DeviceResolver
from cortex.iot.simulator import DeviceSimulator, SimulatedDevice
from cortex.iot.types import DeviceCategory


@pytest.fixture()
async def registry() -> DeviceRegistry:
    reg = DeviceRegistry()
    await reg.initialize()
    return reg


@pytest.fixture()
async def simulator(registry: DeviceRegistry) -> DeviceSimulator:
    sim = DeviceSimulator()
    devices = [
        SimulatedDevice(
            "sim_kitchen_light", "Kitchen Light",
            DeviceCategory.LIGHT, room="kitchen",
        ),
        SimulatedDevice(
            "sim_bedroom_lamp", "Bedroom Lamp",
            DeviceCategory.LIGHT, room="bedroom",
        ),
        SimulatedDevice(
            "sim_kitchen_plug", "Kitchen Plug",
            DeviceCategory.SWITCH, room="kitchen",
        ),
    ]
    for d in devices:
        sim.add_device(d)
        await registry.register_device(d.info)
        await registry.update_state(d.info.id, d.state)
    return sim


class _FakeManager:
    """Minimal IoTManager stand-in for tool tests."""

    def __init__(
        self, simulator: DeviceSimulator, registry: DeviceRegistry,
    ) -> None:
        self._simulator = simulator
        self.registry = registry

    async def send_command(self, command: object) -> bool:
        return await self._simulator.send_command(command)  # type: ignore[arg-type]


@pytest.fixture()
async def manager(simulator: DeviceSimulator, registry: DeviceRegistry) -> _FakeManager:
    return _FakeManager(simulator, registry)


@pytest.fixture()
async def resolver(registry: DeviceRegistry) -> DeviceResolver:
    return DeviceResolver(registry)


@pytest.fixture(autouse=True)
async def _wire_backend(
    manager: _FakeManager, resolver: DeviceResolver,
) -> None:
    set_iot_backend(manager, resolver)
    yield  # type: ignore[misc]
    set_iot_backend(None, None)


# --- DeviceQueryTool ---


class TestDeviceQueryTool:
    def test_schema(self) -> None:
        tool = DeviceQueryTool()
        schema = tool.get_schema()
        assert schema["name"] == "device_query"
        assert "device" in schema["parameters"]["properties"]

    def test_properties(self) -> None:
        tool = DeviceQueryTool()
        assert tool.name == "device_query"
        assert tool.permission_tier == 0

    @pytest.mark.asyncio()
    async def test_no_backend(self) -> None:
        set_iot_backend(None, None)
        tool = DeviceQueryTool()
        result = await tool.execute({"device": "kitchen light"})
        assert result.success is True
        assert "not configured" in result.display_text

    @pytest.mark.asyncio()
    async def test_empty_device(self) -> None:
        tool = DeviceQueryTool()
        result = await tool.execute({"device": ""})
        assert result.success is False
        assert "required" in (result.error or "").lower()

    @pytest.mark.asyncio()
    async def test_missing_device(self) -> None:
        tool = DeviceQueryTool()
        result = await tool.execute({})
        assert result.success is False

    @pytest.mark.asyncio()
    async def test_query_known_device(self) -> None:
        tool = DeviceQueryTool()
        result = await tool.execute({"device": "Kitchen Light"})
        assert result.success is True
        assert result.data["device_id"] == "sim_kitchen_light"
        assert result.data["state"] == "off"
        assert "Kitchen Light" in result.display_text

    @pytest.mark.asyncio()
    async def test_query_unknown_device(self) -> None:
        tool = DeviceQueryTool()
        result = await tool.execute({"device": "Garage Door"})
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio()
    async def test_query_with_brightness(
        self, simulator: DeviceSimulator,
    ) -> None:
        from cortex.iot.types import DeviceCommand

        # Turn on with brightness
        cmd = DeviceCommand(
            device_id="sim_kitchen_light",
            domain="light",
            service="turn_on",
            service_data={"brightness": 200},
        )
        await simulator.send_command(cmd)

        # Update registry state
        state = await simulator.get_state("sim_kitchen_light")
        assert state is not None
        mgr, _ = get_iot_backend()
        await mgr.registry.update_state("sim_kitchen_light", state)

        tool = DeviceQueryTool()
        result = await tool.execute({"device": "Kitchen Light"})
        assert result.success is True
        assert "Brightness" in result.display_text


# --- DeviceControlTool ---


class TestDeviceControlTool:
    def test_schema(self) -> None:
        tool = DeviceControlTool()
        schema = tool.get_schema()
        assert schema["name"] == "device_control"
        assert "device" in schema["parameters"]["properties"]
        assert "action" in schema["parameters"]["properties"]
        assert "brightness" in schema["parameters"]["properties"]

    def test_properties(self) -> None:
        tool = DeviceControlTool()
        assert tool.name == "device_control"
        assert tool.permission_tier == 1

    @pytest.mark.asyncio()
    async def test_no_backend(self) -> None:
        set_iot_backend(None, None)
        tool = DeviceControlTool()
        result = await tool.execute({"device": "light", "action": "turn_on"})
        assert result.success is False
        assert "not configured" in (result.error or "").lower()

    @pytest.mark.asyncio()
    async def test_empty_device(self) -> None:
        tool = DeviceControlTool()
        result = await tool.execute({"device": "", "action": "turn_on"})
        assert result.success is False

    @pytest.mark.asyncio()
    async def test_empty_action(self) -> None:
        tool = DeviceControlTool()
        result = await tool.execute({"device": "Kitchen Light", "action": ""})
        assert result.success is False

    @pytest.mark.asyncio()
    async def test_turn_on(self, simulator: DeviceSimulator) -> None:
        tool = DeviceControlTool()
        result = await tool.execute({
            "device": "Kitchen Light",
            "action": "turn_on",
        })
        assert result.success is True
        assert "turn on" in result.display_text

        state = await simulator.get_state("sim_kitchen_light")
        assert state is not None
        assert state.state == "on"

    @pytest.mark.asyncio()
    async def test_turn_off(self, simulator: DeviceSimulator) -> None:
        tool = DeviceControlTool()
        result = await tool.execute({
            "device": "Kitchen Light",
            "action": "turn_off",
        })
        assert result.success is True

    @pytest.mark.asyncio()
    async def test_with_brightness(self, simulator: DeviceSimulator) -> None:
        tool = DeviceControlTool()
        result = await tool.execute({
            "device": "Kitchen Light",
            "action": "turn_on",
            "brightness": 128,
        })
        assert result.success is True

    @pytest.mark.asyncio()
    async def test_unknown_device(self) -> None:
        tool = DeviceControlTool()
        result = await tool.execute({
            "device": "Garage Door",
            "action": "turn_on",
        })
        assert result.success is False
        assert "not found" in (result.error or "").lower()


# --- DeviceListTool ---


class TestDeviceListTool:
    def test_schema(self) -> None:
        tool = DeviceListTool()
        schema = tool.get_schema()
        assert schema["name"] == "device_list"
        assert "room" in schema["parameters"]["properties"]

    def test_properties(self) -> None:
        tool = DeviceListTool()
        assert tool.name == "device_list"
        assert tool.permission_tier == 0

    @pytest.mark.asyncio()
    async def test_no_backend(self) -> None:
        set_iot_backend(None, None)
        tool = DeviceListTool()
        result = await tool.execute({})
        assert result.success is True
        assert "not configured" in result.display_text

    @pytest.mark.asyncio()
    async def test_list_all(self) -> None:
        tool = DeviceListTool()
        result = await tool.execute({})
        assert result.success is True
        assert len(result.data) == 3
        assert "3 devices" in result.display_text

    @pytest.mark.asyncio()
    async def test_list_by_room(self) -> None:
        tool = DeviceListTool()
        result = await tool.execute({"room": "kitchen"})
        assert result.success is True
        assert len(result.data) == 2
        names = [d["name"] for d in result.data]
        assert "Kitchen Light" in names
        assert "Kitchen Plug" in names

    @pytest.mark.asyncio()
    async def test_list_empty_room(self) -> None:
        tool = DeviceListTool()
        result = await tool.execute({"room": "garage"})
        assert result.success is True
        assert len(result.data) == 0
        assert "No devices" in result.display_text

    @pytest.mark.asyncio()
    async def test_grouped_by_room(self) -> None:
        tool = DeviceListTool()
        result = await tool.execute({})
        assert "kitchen" in result.display_text.lower()
        assert "bedroom" in result.display_text.lower()
