"""IoT manager — lifecycle manager for IoT adapters."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from cortex.iot.protocols import IoTAdapter
from cortex.iot.registry import DeviceRegistry
from cortex.iot.types import DeviceCommand, DeviceState

logger = structlog.get_logger()


class IoTManager:
    """Lifecycle manager for IoT adapters.

    Registers adapters (MQTT, HA, simulator), manages connect/disconnect,
    routes commands to the appropriate adapter, and maintains the device registry.
    """

    def __init__(self, registry: DeviceRegistry | None = None) -> None:
        self._adapters: dict[str, IoTAdapter] = {}
        self._registry = registry or DeviceRegistry()
        self._state_callbacks: list[Callable[[str, DeviceState], Any]] = []
        self._started = False

    def register_adapter(self, adapter: IoTAdapter) -> None:
        """Register an IoT adapter."""
        adapter_type = adapter.adapter_type
        self._adapters[adapter_type] = adapter
        adapter.subscribe_state(self._on_state_change)
        logger.info("IoT adapter registered", adapter_type=adapter_type)

    async def start(self) -> None:
        """Connect all adapters and initialize registry."""
        await self._registry.initialize()

        for adapter_type, adapter in self._adapters.items():
            try:
                await adapter.connect()
                devices = await adapter.get_devices()
                for device in devices:
                    await self._registry.register_device(device)
                logger.info(
                    "IoT adapter connected",
                    adapter_type=adapter_type,
                    device_count=len(devices),
                )
            except Exception:
                logger.exception("IoT adapter failed to connect", adapter_type=adapter_type)

        self._started = True
        logger.info("IoT manager started", adapter_count=len(self._adapters))

    async def stop(self) -> None:
        """Disconnect all adapters."""
        for adapter_type, adapter in self._adapters.items():
            try:
                await adapter.disconnect()
                logger.info("IoT adapter disconnected", adapter_type=adapter_type)
            except Exception:
                logger.exception(
                    "IoT adapter failed to disconnect",
                    adapter_type=adapter_type,
                )
        self._started = False
        logger.info("IoT manager stopped")

    async def send_command(self, command: DeviceCommand) -> bool:
        """Route a command to the appropriate adapter.

        Determines the adapter from the device's source in the registry.
        """
        device = self._registry.get_device(command.device_id)
        if device is None:
            logger.warning("Command for unknown device", device_id=command.device_id)
            return False

        adapter_type = device.source.value
        adapter = self._adapters.get(adapter_type)
        if adapter is None:
            logger.warning(
                "No adapter for device source",
                device_id=command.device_id,
                source=adapter_type,
            )
            return False

        try:
            result = await adapter.send_command(command)
            logger.info(
                "Command sent",
                device_id=command.device_id,
                service=command.service,
                success=result,
            )
            return result
        except Exception:
            logger.exception("Command failed", device_id=command.device_id)
            return False

    def subscribe_state(self, callback: Callable[[str, DeviceState], Any]) -> None:
        """Subscribe to device state changes from all adapters."""
        self._state_callbacks.append(callback)

    def _on_state_change(self, device_id: str, state: DeviceState) -> None:
        """Handle state change from any adapter."""
        for callback in self._state_callbacks:
            try:
                callback(device_id, state)
            except Exception:
                logger.exception("State change callback error", device_id=device_id)

    @property
    def registry(self) -> DeviceRegistry:
        return self._registry

    @property
    def adapter_types(self) -> list[str]:
        return list(self._adapters.keys())

    @property
    def is_started(self) -> bool:
        return self._started

    async def health_check(self) -> dict[str, bool]:
        """Check health of all adapters."""
        results: dict[str, bool] = {}
        for adapter_type, adapter in self._adapters.items():
            try:
                results[adapter_type] = await adapter.health_check()
            except Exception:
                results[adapter_type] = False
        return results
