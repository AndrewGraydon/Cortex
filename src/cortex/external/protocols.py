"""External service protocols and lifecycle management."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import structlog

from cortex.external.types import ServiceStatus

logger = structlog.get_logger()


@runtime_checkable
class ExternalServiceAdapter(Protocol):
    """Provider-agnostic external service interface (DD-035).

    All external services (calendar, email, messaging, tasks) implement
    this protocol. Concrete implementations wrap provider-specific APIs
    (CalDAV, IMAP, ntfy, etc.) behind a uniform lifecycle interface.
    """

    async def connect(self) -> None:
        """Establish connection to the external service."""
        ...

    async def disconnect(self) -> None:
        """Gracefully disconnect from the external service."""
        ...

    async def health_check(self) -> bool:
        """Check if the service is reachable and functional.

        Returns True if healthy, False otherwise.
        """
        ...

    @property
    def service_type(self) -> str:
        """Service category: 'calendar', 'messaging', 'email', 'tasks'."""
        ...


class ExternalServiceManager:
    """Lifecycle manager for all external service adapters.

    Registers adapters, manages connect/disconnect lifecycle,
    and exposes health status for the dashboard.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, ExternalServiceAdapter] = {}
        self._status: dict[str, ServiceStatus] = {}

    def register(self, adapter: ExternalServiceAdapter) -> None:
        """Register an adapter. Overwrites if same service_type exists."""
        stype = adapter.service_type
        self._adapters[stype] = adapter
        self._status[stype] = ServiceStatus.DISCONNECTED
        logger.info("Registered external service", service_type=stype)

    async def start_all(self) -> None:
        """Connect all registered adapters. Failures are logged, not raised."""
        for stype, adapter in self._adapters.items():
            try:
                await adapter.connect()
                self._status[stype] = ServiceStatus.CONNECTED
                logger.info("External service connected", service_type=stype)
            except Exception:
                self._status[stype] = ServiceStatus.ERROR
                logger.exception("External service failed to connect", service_type=stype)

    async def stop_all(self) -> None:
        """Disconnect all registered adapters."""
        for stype, adapter in self._adapters.items():
            try:
                await adapter.disconnect()
                self._status[stype] = ServiceStatus.DISCONNECTED
                logger.info("External service disconnected", service_type=stype)
            except Exception:
                logger.exception("External service failed to disconnect", service_type=stype)

    async def health_check_all(self) -> dict[str, ServiceStatus]:
        """Check health of all registered adapters.

        Returns a dict of service_type -> ServiceStatus.
        """
        result: dict[str, ServiceStatus] = {}
        for stype, adapter in self._adapters.items():
            try:
                healthy = await adapter.health_check()
                status = ServiceStatus.CONNECTED if healthy else ServiceStatus.ERROR
            except Exception:
                status = ServiceStatus.ERROR
                logger.exception("Health check failed", service_type=stype)
            self._status[stype] = status
            result[stype] = status
        return result

    def get(self, service_type: str) -> ExternalServiceAdapter | None:
        """Get a registered adapter by service type."""
        return self._adapters.get(service_type)

    def get_status(self, service_type: str) -> ServiceStatus:
        """Get the last known status for a service type."""
        return self._status.get(service_type, ServiceStatus.DISABLED)

    @property
    def registered_types(self) -> list[str]:
        """List of registered service types."""
        return list(self._adapters.keys())

    def __len__(self) -> int:
        return len(self._adapters)
