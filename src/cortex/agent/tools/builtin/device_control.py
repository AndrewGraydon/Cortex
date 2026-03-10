"""Device control tools — query and control IoT devices. Tier 0/1.

Wired to IoTManager. Falls back to stub responses if not configured.
"""

from __future__ import annotations

import logging
from typing import Any

from cortex.agent.types import ToolResult

logger = logging.getLogger(__name__)

# Module-level backend — set via set_iot_backend()
_manager: Any = None
_resolver: Any = None


def set_iot_backend(manager: Any, resolver: Any = None) -> None:
    """Wire the device tools to an IoT manager and resolver."""
    global _manager, _resolver  # noqa: PLW0603
    _manager = manager
    _resolver = resolver


def get_iot_backend() -> tuple[Any, Any]:
    """Get the current IoT backend (for testing)."""
    return _manager, _resolver


class DeviceQueryTool:
    """Query device state. Tier 0 (safe, read-only)."""

    @property
    def name(self) -> str:
        return "device_query"

    @property
    def description(self) -> str:
        return "Get the state of a smart home device"

    @property
    def permission_tier(self) -> int:
        return 0

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "device_query",
            "description": "Get the state of a smart home device",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {
                        "type": "string",
                        "description": "Device name or ID",
                    },
                },
                "required": ["device"],
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if _manager is None:
            return ToolResult(
                tool_name="device_query",
                success=True,
                data={},
                display_text="Smart home devices are not configured.",
            )

        device_ref = arguments.get("device", "").strip()
        if not device_ref:
            return ToolResult(
                tool_name="device_query",
                success=False,
                error="Device name or ID is required.",
            )

        # Resolve device name
        device_info = None
        if _resolver is not None:
            result = _resolver.resolve(device_ref)
            if result.ambiguous:
                names = [c.device.friendly_name for c in result.candidates[:3]]
                return ToolResult(
                    tool_name="device_query",
                    success=False,
                    error=f"Multiple devices match. Did you mean: {', '.join(names)}?",
                )
            device_info = result.best

        if device_info is None:
            device_info = _manager.registry.get_device(device_ref)

        if device_info is None:
            return ToolResult(
                tool_name="device_query",
                success=False,
                error=f"Device '{device_ref}' not found.",
            )

        state = _manager.registry.get_state(device_info.id)
        state_str = state.state if state else "unknown"
        attrs = state.attributes if state else {}

        data = {
            "device_id": device_info.id,
            "name": device_info.friendly_name,
            "state": state_str,
            "attributes": attrs,
            "category": device_info.category.value,
            "room": device_info.room,
        }

        display = f"{device_info.friendly_name} is {state_str}."
        if attrs.get("brightness"):
            display += f" Brightness: {attrs['brightness']}."

        return ToolResult(
            tool_name="device_query",
            success=True,
            data=data,
            display_text=display,
        )


class DeviceControlTool:
    """Control a device (turn on/off, set brightness, etc.). Tier 1."""

    @property
    def name(self) -> str:
        return "device_control"

    @property
    def description(self) -> str:
        return "Control a smart home device"

    @property
    def permission_tier(self) -> int:
        return 1

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "device_control",
            "description": "Control a smart home device",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {
                        "type": "string",
                        "description": "Device name or ID",
                    },
                    "action": {
                        "type": "string",
                        "description": "Action: turn_on, turn_off, toggle",
                    },
                    "brightness": {
                        "type": "integer",
                        "description": "Brightness 0-255 (optional)",
                    },
                },
                "required": ["device", "action"],
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if _manager is None:
            return ToolResult(
                tool_name="device_control",
                success=False,
                error="Smart home devices are not configured.",
            )

        device_ref = arguments.get("device", "").strip()
        action = arguments.get("action", "").strip()

        if not device_ref:
            return ToolResult(
                tool_name="device_control",
                success=False,
                error="Device name or ID is required.",
            )
        if not action:
            return ToolResult(
                tool_name="device_control",
                success=False,
                error="Action is required.",
            )

        # Resolve device name
        device_info = None
        if _resolver is not None:
            result = _resolver.resolve(device_ref)
            if result.ambiguous:
                names = [c.device.friendly_name for c in result.candidates[:3]]
                return ToolResult(
                    tool_name="device_control",
                    success=False,
                    error=f"Multiple devices match. Did you mean: {', '.join(names)}?",
                )
            device_info = result.best

        if device_info is None:
            device_info = _manager.registry.get_device(device_ref)

        if device_info is None:
            return ToolResult(
                tool_name="device_control",
                success=False,
                error=f"Device '{device_ref}' not found.",
            )

        # Build command
        from cortex.iot.types import DeviceCommand  # noqa: PLC0415

        service_data: dict[str, Any] = {}
        brightness = arguments.get("brightness")
        if brightness is not None:
            service_data["brightness"] = brightness

        command = DeviceCommand(
            device_id=device_info.id,
            domain=device_info.category.value,
            service=action,
            service_data=service_data,
        )

        try:
            success = await _manager.send_command(command)
            if success:
                return ToolResult(
                    tool_name="device_control",
                    success=True,
                    data={"device_id": device_info.id, "action": action},
                    display_text=f"Done. {device_info.friendly_name} {action.replace('_', ' ')}.",
                )
            return ToolResult(
                tool_name="device_control",
                success=False,
                error=f"Failed to {action} {device_info.friendly_name}.",
            )
        except Exception as e:
            logger.exception("Device control failed")
            return ToolResult(
                tool_name="device_control",
                success=False,
                error=str(e),
            )


class DeviceListTool:
    """List devices grouped by room. Tier 0."""

    @property
    def name(self) -> str:
        return "device_list"

    @property
    def description(self) -> str:
        return "List smart home devices"

    @property
    def permission_tier(self) -> int:
        return 0

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "device_list",
            "description": "List smart home devices",
            "parameters": {
                "type": "object",
                "properties": {
                    "room": {
                        "type": "string",
                        "description": "Filter by room (optional)",
                    },
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if _manager is None:
            return ToolResult(
                tool_name="device_list",
                success=True,
                data=[],
                display_text="Smart home devices are not configured.",
            )

        room = arguments.get("room", "").strip()

        devices = _manager.registry.get_by_room(room) if room else _manager.registry.get_all()

        if not devices:
            display = f"No devices found{' in ' + room if room else ''}."
            return ToolResult(
                tool_name="device_list",
                success=True,
                data=[],
                display_text=display,
            )

        data = [
            {
                "id": d.id,
                "name": d.friendly_name,
                "category": d.category.value,
                "room": d.room,
            }
            for d in devices
        ]

        # Group by room for display
        rooms: dict[str, list[str]] = {}
        for d in devices:
            r = d.room or "unassigned"
            rooms.setdefault(r, []).append(d.friendly_name)

        parts = []
        for r, names in rooms.items():
            parts.append(f"{r}: {', '.join(names)}")
        display = f"You have {len(devices)} devices. " + ". ".join(parts) + "."

        return ToolResult(
            tool_name="device_list",
            success=True,
            data=data,
            display_text=display,
        )
