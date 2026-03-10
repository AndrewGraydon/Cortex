"""MQTT auto-discovery — parse HA MQTT Discovery and Zigbee2MQTT messages."""

from __future__ import annotations

import json
from typing import Any

import structlog

from cortex.iot.types import (
    DeviceCapability,
    DeviceCategory,
    DeviceInfo,
    DeviceSource,
)

logger = structlog.get_logger()

# HA MQTT Discovery component → DeviceCategory
_HA_CATEGORY_MAP: dict[str, DeviceCategory] = {
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


def parse_ha_discovery(topic: str, payload: bytes) -> DeviceInfo | None:
    """Parse a Home Assistant MQTT Discovery config message.

    Topic format: homeassistant/<component>/<node_id>/config
    Payload: JSON with device info.

    Returns DeviceInfo or None if unparseable.
    """
    try:
        parts = topic.split("/")
        if len(parts) < 4 or parts[0] != "homeassistant" or parts[-1] != "config":
            return None

        component = parts[1]
        node_id = parts[2]

        data = json.loads(payload)
        if not isinstance(data, dict):
            return None

        device_id = data.get("unique_id", node_id)
        name = data.get("name", node_id)
        category = _HA_CATEGORY_MAP.get(component, DeviceCategory.UNKNOWN)

        # Extract device metadata
        device_block = data.get("device", {})
        manufacturer = device_block.get("manufacturer", "")
        model = device_block.get("model", "")

        # Extract command topic
        mqtt_topic = str(data.get("command_topic", data.get("state_topic", "")) or "")

        # Extract capabilities from available fields
        capabilities = _extract_ha_capabilities(component, data)

        return DeviceInfo(
            id=device_id,
            name=name,
            friendly_name=name,
            category=category,
            source=DeviceSource.MQTT,
            capabilities=capabilities,
            mqtt_topic=mqtt_topic,
            manufacturer=manufacturer,
            model=model,
        )
    except Exception:
        logger.exception("Failed to parse HA discovery", topic=topic)
        return None


def parse_z2m_devices(payload: bytes) -> list[DeviceInfo]:
    """Parse Zigbee2MQTT bridge/devices message.

    Payload: JSON array of device objects.
    """
    try:
        data = json.loads(payload)
        if not isinstance(data, list):
            return []

        devices: list[DeviceInfo] = []
        for item in data:
            if not isinstance(item, dict):
                continue

            ieee = item.get("ieee_address", "")
            friendly_name = str(item.get("friendly_name", ieee))
            definition = item.get("definition") or {}

            # Determine category from definition
            category = _z2m_category(definition)

            device = DeviceInfo(
                id=f"z2m_{ieee}" if ieee else f"z2m_{friendly_name}",
                name=friendly_name,
                friendly_name=friendly_name,
                category=category,
                source=DeviceSource.MQTT,
                mqtt_topic=f"zigbee2mqtt/{friendly_name}",
                manufacturer=definition.get("vendor", ""),
                model=definition.get("model", ""),
            )
            devices.append(device)

        return devices
    except Exception:
        logger.exception("Failed to parse Z2M devices")
        return []


def _extract_ha_capabilities(
    component: str,
    data: dict[str, Any],
) -> list[DeviceCapability]:
    """Extract capabilities from HA discovery data."""
    caps: list[DeviceCapability] = []

    if component == "light":
        caps.append(DeviceCapability(name="state", value_type="bool"))
        if "brightness_command_topic" in data or "brightness_scale" in data:
            caps.append(DeviceCapability(
                name="brightness",
                value_type="int",
                min_value=0,
                max_value=data.get("brightness_scale", 255),
            ))
        if "color_temp_command_topic" in data:
            caps.append(DeviceCapability(name="color_temp", value_type="int"))
    elif component == "switch":
        caps.append(DeviceCapability(name="state", value_type="bool"))
    elif component == "climate":
        caps.append(DeviceCapability(name="state", value_type="bool"))
        caps.append(DeviceCapability(name="target_temperature", value_type="float"))
        modes = data.get("modes", [])
        if modes:
            caps.append(DeviceCapability(
                name="mode",
                value_type="enum",
                enum_values=modes,
            ))
    elif component == "cover":
        caps.append(DeviceCapability(name="state", value_type="bool"))
        if "position_topic" in data:
            caps.append(DeviceCapability(
                name="position",
                value_type="int",
                min_value=0,
                max_value=100,
            ))
    elif component in ("sensor", "binary_sensor"):
        unit = data.get("unit_of_measurement", "")
        caps.append(DeviceCapability(name="value", value_type="float" if unit else "string"))

    return caps


def _z2m_category(definition: dict[str, Any]) -> DeviceCategory:
    """Determine device category from Z2M definition."""
    desc = definition.get("description", "").lower()

    if any(w in desc for w in ["light", "bulb", "lamp", "led"]):
        return DeviceCategory.LIGHT
    if any(w in desc for w in ["switch", "plug", "outlet", "relay"]):
        return DeviceCategory.SWITCH
    if any(w in desc for w in ["sensor", "temperature", "humidity", "motion"]):
        return DeviceCategory.SENSOR
    if any(w in desc for w in ["thermostat", "climate", "hvac"]):
        return DeviceCategory.CLIMATE
    if any(w in desc for w in ["curtain", "blind", "shade", "cover"]):
        return DeviceCategory.COVER
    if any(w in desc for w in ["lock"]):
        return DeviceCategory.LOCK
    if any(w in desc for w in ["fan"]):
        return DeviceCategory.FAN

    return DeviceCategory.UNKNOWN
