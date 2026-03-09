"""FastAPI dependency injection — provides config, services, and DB to routes."""

from __future__ import annotations

from typing import Any

from cortex.agent.health import HealthMonitor
from cortex.config import CortexConfig
from cortex.external.protocols import ExternalServiceManager


class ServiceContainer:
    """Holds references to shared services for dependency injection.

    Set up once during app startup (lifespan), then injected into routes
    via FastAPI's Depends().
    """

    def __init__(self) -> None:
        self.config: CortexConfig = CortexConfig()
        self.health_monitor: HealthMonitor = HealthMonitor()
        self._extras: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        """Store an arbitrary service by key."""
        self._extras[key] = value

    def get(self, key: str) -> Any:
        """Retrieve a service by key. Returns None if not found."""
        return self._extras.get(key)


# Module-level singleton — populated at app startup
_container: ServiceContainer | None = None


def init_services(config: CortexConfig, **kwargs: Any) -> ServiceContainer:
    """Initialize the service container. Called once during app lifespan."""
    global _container  # noqa: PLW0603
    container = ServiceContainer()
    container.config = config
    container.health_monitor = HealthMonitor(
        npu=kwargs.get("npu"),
        poll_interval_s=config.health.npu_poll_interval,
    )
    # External service manager (Phase 3b)
    ext_manager = kwargs.pop("external_service_manager", None)
    if ext_manager is None:
        ext_manager = ExternalServiceManager()
    container.set("external_service_manager", ext_manager)

    for key, value in kwargs.items():
        container.set(key, value)
    _container = container
    return container


def get_services() -> ServiceContainer:
    """FastAPI dependency — returns the service container."""
    if _container is None:
        msg = "Services not initialized — call init_services() during app startup"
        raise RuntimeError(msg)
    return _container


def get_config() -> CortexConfig:
    """FastAPI dependency — returns the app config."""
    return get_services().config


def get_health_monitor() -> HealthMonitor:
    """FastAPI dependency — returns the health monitor."""
    return get_services().health_monitor
