"""Tests for device registry — CRUD, lookup, state cache."""

from __future__ import annotations

from cortex.iot.registry import DeviceRegistry
from cortex.iot.types import (
    DeviceCategory,
    DeviceInfo,
    DeviceState,
)


def _make_device(
    device_id: str = "d1",
    name: str = "Test Light",
    category: DeviceCategory = DeviceCategory.LIGHT,
    room: str = "living_room",
    **kwargs: object,
) -> DeviceInfo:
    return DeviceInfo(
        id=device_id,
        name=name,
        category=category,
        room=room,
        **kwargs,  # type: ignore[arg-type]
    )


class TestRegistryInit:
    async def test_initialize_without_db(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()
        assert registry.device_count == 0

    async def test_initialize_with_sqlite(self) -> None:
        import aiosqlite

        db = await aiosqlite.connect(":memory:")
        try:
            registry = DeviceRegistry(db=db)
            await registry.initialize()
            assert registry.device_count == 0
        finally:
            await db.close()


class TestRegistryRegister:
    async def test_register_device(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()

        device = _make_device()
        await registry.register_device(device)
        assert registry.device_count == 1

    async def test_register_multiple(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()

        await registry.register_device(_make_device("d1"))
        await registry.register_device(_make_device("d2", name="Switch"))
        assert registry.device_count == 2

    async def test_register_overwrites(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()

        await registry.register_device(_make_device("d1", name="Old Name"))
        await registry.register_device(_make_device("d1", name="New Name"))
        assert registry.device_count == 1
        assert registry.get_device("d1") is not None
        assert registry.get_device("d1").name == "New Name"  # type: ignore[union-attr]

    async def test_register_creates_default_state(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()

        await registry.register_device(_make_device())
        state = registry.get_state("d1")
        assert state is not None
        assert state.state == "unknown"


class TestRegistryLookup:
    async def test_get_device(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()
        await registry.register_device(_make_device())

        device = registry.get_device("d1")
        assert device is not None
        assert device.name == "Test Light"

    async def test_get_nonexistent(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()
        assert registry.get_device("missing") is None

    async def test_get_by_name_exact(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()
        await registry.register_device(_make_device("d1", name="Kitchen Light"))

        results = registry.get_by_name("Kitchen Light")
        assert len(results) == 1

    async def test_get_by_name_partial(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()
        await registry.register_device(_make_device("d1", name="Kitchen Light"))
        await registry.register_device(_make_device("d2", name="Kitchen Switch"))
        await registry.register_device(_make_device("d3", name="Bedroom Light"))

        results = registry.get_by_name("kitchen")
        assert len(results) == 2

    async def test_get_by_name_friendly_name(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()
        await registry.register_device(
            DeviceInfo(id="d1", name="light_001", friendly_name="Desk Lamp")
        )

        results = registry.get_by_name("desk")
        assert len(results) == 1

    async def test_get_by_room(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()
        await registry.register_device(_make_device("d1", room="kitchen"))
        await registry.register_device(_make_device("d2", room="kitchen"))
        await registry.register_device(_make_device("d3", room="bedroom"))

        results = registry.get_by_room("kitchen")
        assert len(results) == 2

    async def test_get_by_room_case_insensitive(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()
        await registry.register_device(_make_device("d1", room="Kitchen"))

        results = registry.get_by_room("kitchen")
        assert len(results) == 1

    async def test_get_by_category(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()
        await registry.register_device(_make_device("d1", category=DeviceCategory.LIGHT))
        await registry.register_device(_make_device("d2", category=DeviceCategory.SWITCH))
        await registry.register_device(_make_device("d3", category=DeviceCategory.LIGHT))

        results = registry.get_by_category(DeviceCategory.LIGHT)
        assert len(results) == 2

    async def test_get_all(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()
        await registry.register_device(_make_device("d1"))
        await registry.register_device(_make_device("d2"))

        all_devices = registry.get_all()
        assert len(all_devices) == 2


class TestRegistryState:
    async def test_update_state(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()
        await registry.register_device(_make_device())

        state = DeviceState(device_id="d1", state="on", attributes={"brightness": 200})
        await registry.update_state("d1", state)

        cached = registry.get_state("d1")
        assert cached is not None
        assert cached.state == "on"
        assert cached.attributes["brightness"] == 200

    async def test_update_state_unknown_device(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()

        state = DeviceState(device_id="unknown", state="on")
        await registry.update_state("unknown", state)
        # Should not crash, just log warning
        assert registry.get_state("unknown") is None


class TestRegistryRemove:
    async def test_remove_existing(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()
        await registry.register_device(_make_device())

        removed = await registry.remove_device("d1")
        assert removed is True
        assert registry.device_count == 0
        assert registry.get_device("d1") is None

    async def test_remove_nonexistent(self) -> None:
        registry = DeviceRegistry()
        await registry.initialize()

        removed = await registry.remove_device("missing")
        assert removed is False


class TestRegistrySQLitePersistence:
    async def test_persist_and_reload(self) -> None:
        import aiosqlite

        db = await aiosqlite.connect(":memory:")
        try:
            # Register a device
            registry1 = DeviceRegistry(db=db)
            await registry1.initialize()
            await registry1.register_device(_make_device("d1", name="Persisted"))
            await registry1.update_state(
                "d1", DeviceState(device_id="d1", state="on")
            )

            # Create new registry with same db — should reload
            registry2 = DeviceRegistry(db=db)
            await registry2.initialize()
            assert registry2.device_count == 1

            device = registry2.get_device("d1")
            assert device is not None
            assert device.name == "Persisted"

            state = registry2.get_state("d1")
            assert state is not None
            assert state.state == "on"
        finally:
            await db.close()
