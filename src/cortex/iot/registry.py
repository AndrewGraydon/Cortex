"""Device registry — SQLite-backed device CRUD and state cache."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any

import structlog

from cortex.iot.types import (
    DeviceCapability,
    DeviceCategory,
    DeviceInfo,
    DeviceSource,
    DeviceState,
)

logger = structlog.get_logger()

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    friendly_name TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'unknown',
    room TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manual',
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    mqtt_topic TEXT NOT NULL DEFAULT '',
    manufacturer TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'unknown',
    attributes_json TEXT NOT NULL DEFAULT '{}',
    last_seen REAL,
    online INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
"""


class DeviceRegistry:
    """SQLite-backed device registry with in-memory state cache.

    Stores device metadata persistently and caches current state.
    Supports lookup by name, ID, room, and category.
    """

    def __init__(self, db: Any = None) -> None:
        self._db = db
        self._devices: dict[str, DeviceInfo] = {}
        self._states: dict[str, DeviceState] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Create tables if using SQLite backend."""
        if self._db is not None:
            await self._db.execute(_CREATE_TABLE_SQL)
            await self._db.commit()
            await self._load_from_db()
        self._initialized = True

    async def _load_from_db(self) -> None:
        """Load all devices from SQLite into memory cache."""
        if self._db is None:
            return
        cursor = await self._db.execute("SELECT * FROM devices")
        rows = await cursor.fetchall()
        for row in rows:
            info = _row_to_device_info(row)
            state = _row_to_device_state(row)
            self._devices[info.id] = info
            self._states[info.id] = state

    async def register_device(self, info: DeviceInfo) -> None:
        """Register or update a device."""
        now = time.time()
        self._devices[info.id] = info

        if info.id not in self._states:
            self._states[info.id] = DeviceState(device_id=info.id)

        if self._db is not None:
            caps_json = json.dumps([
                {"name": c.name, "value_type": c.value_type}
                for c in info.capabilities
            ])
            await self._db.execute(
                """INSERT OR REPLACE INTO devices
                   (id, name, friendly_name, category, room, source,
                    capabilities_json, mqtt_topic, manufacturer, model,
                    state, attributes_json, last_seen, online, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    info.id, info.name, info.friendly_name,
                    info.category.value, info.room, info.source.value,
                    caps_json, info.mqtt_topic, info.manufacturer, info.model,
                    self._states[info.id].state,
                    json.dumps(self._states[info.id].attributes),
                    now, 1, now, now,
                ),
            )
            await self._db.commit()

        logger.debug("Device registered", device_id=info.id, name=info.name)

    async def update_state(self, device_id: str, state: DeviceState) -> None:
        """Update the state of a registered device."""
        if device_id not in self._devices:
            logger.warning("State update for unknown device", device_id=device_id)
            return

        self._states[device_id] = state

        if self._db is not None:
            now = time.time()
            await self._db.execute(
                """UPDATE devices SET state=?, attributes_json=?,
                   last_seen=?, online=?, updated_at=? WHERE id=?""",
                (
                    state.state,
                    json.dumps(state.attributes),
                    now, int(state.online), now,
                    device_id,
                ),
            )
            await self._db.commit()

    def get_device(self, device_id: str) -> DeviceInfo | None:
        """Get device info by ID."""
        return self._devices.get(device_id)

    def get_state(self, device_id: str) -> DeviceState | None:
        """Get current state of a device."""
        return self._states.get(device_id)

    def get_by_name(self, name: str) -> list[DeviceInfo]:
        """Find devices by name (case-insensitive substring match)."""
        name_lower = name.lower()
        return [
            d for d in self._devices.values()
            if name_lower in d.name.lower() or name_lower in d.friendly_name.lower()
        ]

    def get_by_room(self, room: str) -> list[DeviceInfo]:
        """Find devices by room (case-insensitive)."""
        room_lower = room.lower()
        return [
            d for d in self._devices.values()
            if d.room.lower() == room_lower
        ]

    def get_by_category(self, category: DeviceCategory) -> list[DeviceInfo]:
        """Find devices by category."""
        return [d for d in self._devices.values() if d.category == category]

    def get_all(self) -> list[DeviceInfo]:
        """Get all registered devices."""
        return list(self._devices.values())

    async def remove_device(self, device_id: str) -> bool:
        """Remove a device from the registry."""
        if device_id not in self._devices:
            return False

        del self._devices[device_id]
        self._states.pop(device_id, None)

        if self._db is not None:
            await self._db.execute("DELETE FROM devices WHERE id=?", (device_id,))
            await self._db.commit()

        logger.debug("Device removed", device_id=device_id)
        return True

    @property
    def device_count(self) -> int:
        return len(self._devices)


def _row_to_device_info(row: Any) -> DeviceInfo:
    """Convert a SQLite row to DeviceInfo."""
    caps_raw = json.loads(row[6]) if row[6] else []
    capabilities = [
        DeviceCapability(name=c.get("name", ""), value_type=c.get("value_type", "bool"))
        for c in caps_raw
    ]
    return DeviceInfo(
        id=row[0],
        name=row[1],
        friendly_name=row[2],
        category=DeviceCategory(row[3]) if row[3] else DeviceCategory.UNKNOWN,
        room=row[4],
        source=DeviceSource(row[5]) if row[5] else DeviceSource.MANUAL,
        capabilities=capabilities,
        mqtt_topic=row[7],
        manufacturer=row[8],
        model=row[9],
    )


def _row_to_device_state(row: Any) -> DeviceState:
    """Convert a SQLite row to DeviceState."""
    attrs = json.loads(row[11]) if row[11] else {}
    last_seen = datetime.fromtimestamp(row[12], tz=UTC) if row[12] else None
    return DeviceState(
        device_id=row[0],
        state=row[10],
        attributes=attrs,
        last_seen=last_seen,
        online=bool(row[13]),
    )
