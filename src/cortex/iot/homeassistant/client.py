"""Home Assistant REST API client — async httpx-based.

Connects to HA via long-lived access token. Reads entity states
and calls services. Implements IoTAdapter protocol.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import structlog

from cortex.iot.types import (
    DeviceCategory,
    DeviceCommand,
    DeviceInfo,
    DeviceSource,
    DeviceState,
)

logger = structlog.get_logger()

# HA domain → DeviceCategory
_HA_DOMAIN_MAP: dict[str, DeviceCategory] = {
    "light": DeviceCategory.LIGHT,
    "switch": DeviceCategory.SWITCH,
    "sensor": DeviceCategory.SENSOR,
    "binary_sensor": DeviceCategory.SENSOR,
    "cover": DeviceCategory.COVER,
    "climate": DeviceCategory.CLIMATE,
    "media_player": DeviceCategory.MEDIA_PLAYER,
    "lock": DeviceCategory.LOCK,
    "fan": DeviceCategory.FAN,
}


class HomeAssistantClient:
    """Home Assistant REST API client.

    Implements IoTAdapter protocol. Uses long-lived access token
    from HA_TOKEN environment variable.
    """

    def __init__(self, url: str, token_env: str = "HA_TOKEN") -> None:
        self._url = url.rstrip("/")
        self._token_env = token_env
        self._client: Any = None
        self._connected = False
        self._devices: dict[str, DeviceInfo] = {}
        self._states: dict[str, DeviceState] = {}
        self._state_callbacks: list[Callable[[str, DeviceState], Any]] = []

    async def connect(self) -> None:
        """Initialize httpx client and verify connection."""
        try:
            import httpx  # noqa: PLC0415

            token = os.environ.get(self._token_env, "")
            if not token:
                msg = f"{self._token_env} environment variable not set"
                raise RuntimeError(msg)

            self._client = httpx.AsyncClient(
                base_url=self._url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=10.0,
            )

            # Verify connection
            response = await self._client.get("/api/")
            response.raise_for_status()
            self._connected = True
            logger.info("Home Assistant connected", url=self._url)
        except Exception:
            self._connected = False
            logger.exception("Home Assistant connection failed", url=self._url)
            raise

    async def disconnect(self) -> None:
        """Close httpx client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._connected = False
        logger.info("Home Assistant disconnected")

    async def health_check(self) -> bool:
        """Check if HA API is reachable."""
        if not self._connected or self._client is None:
            return False
        try:
            response = await self._client.get("/api/")
            return bool(response.status_code == 200)
        except Exception:
            return False

    async def send_command(self, command: DeviceCommand) -> bool:
        """Call a HA service."""
        if self._client is None or not self._connected:
            return False

        url = f"/api/services/{command.domain}/{command.service}"
        data = {"entity_id": command.device_id, **command.service_data}

        try:
            response = await self._client.post(url, json=data)
            success = bool(response.status_code == 200)
            if success:
                logger.info(
                    "HA service called",
                    domain=command.domain,
                    service=command.service,
                    entity_id=command.device_id,
                )
            return success
        except Exception:
            logger.exception("HA service call failed")
            return False

    async def get_devices(self) -> list[DeviceInfo]:
        """Fetch all entity states from HA and convert to DeviceInfo."""
        if self._client is None or not self._connected:
            return []

        try:
            response = await self._client.get("/api/states")
            response.raise_for_status()
            entities = response.json()

            devices: list[DeviceInfo] = []
            for entity in entities:
                info = _entity_to_device_info(entity)
                if info is not None:
                    devices.append(info)
                    self._devices[info.id] = info

                    state = _entity_to_device_state(entity)
                    self._states[info.id] = state

            return devices
        except Exception:
            logger.exception("HA get_devices failed")
            return []

    async def get_state(self, device_id: str) -> DeviceState | None:
        """Get current state of an entity from HA."""
        if self._client is None or not self._connected:
            return self._states.get(device_id)

        try:
            response = await self._client.get(f"/api/states/{device_id}")
            if response.status_code != 200:
                return None
            entity = response.json()
            state = _entity_to_device_state(entity)
            self._states[device_id] = state
            return state
        except Exception:
            logger.exception("HA get_state failed", device_id=device_id)
            return self._states.get(device_id)

    def subscribe_state(
        self,
        callback: Callable[[str, DeviceState], Any],
    ) -> None:
        """Subscribe to state change notifications."""
        self._state_callbacks.append(callback)

    @property
    def adapter_type(self) -> str:
        return "homeassistant"


def _entity_to_device_info(entity: dict[str, Any]) -> DeviceInfo | None:
    """Convert a HA entity state dict to DeviceInfo."""
    entity_id = entity.get("entity_id", "")
    if not entity_id:
        return None

    parts = entity_id.split(".", 1)
    domain = parts[0] if parts else ""
    category = _HA_DOMAIN_MAP.get(domain, DeviceCategory.UNKNOWN)

    attrs = entity.get("attributes", {})
    friendly_name = str(attrs.get("friendly_name", entity_id))

    return DeviceInfo(
        id=entity_id,
        name=entity_id,
        friendly_name=friendly_name,
        category=category,
        source=DeviceSource.HOMEASSISTANT,
    )


def _entity_to_device_state(entity: dict[str, Any]) -> DeviceState:
    """Convert a HA entity state dict to DeviceState."""
    entity_id = entity.get("entity_id", "")
    state_val = entity.get("state", "unknown")
    attrs = entity.get("attributes", {})

    return DeviceState(
        device_id=entity_id,
        state=state_val,
        attributes=attrs,
        online=state_val != "unavailable",
    )
