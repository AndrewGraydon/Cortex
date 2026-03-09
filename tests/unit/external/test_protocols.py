"""Tests for external service protocols and manager."""

from __future__ import annotations

import pytest

from cortex.external.protocols import ExternalServiceAdapter, ExternalServiceManager
from cortex.external.types import ServiceStatus


class MockCalendarAdapter:
    """Mock calendar adapter for testing."""

    def __init__(self, *, healthy: bool = True, fail_connect: bool = False) -> None:
        self._healthy = healthy
        self._fail_connect = fail_connect
        self.connected = False
        self.disconnect_called = False

    async def connect(self) -> None:
        if self._fail_connect:
            msg = "Connection refused"
            raise ConnectionError(msg)
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False
        self.disconnect_called = True

    async def health_check(self) -> bool:
        return self._healthy

    @property
    def service_type(self) -> str:
        return "calendar"


class MockEmailAdapter:
    """Mock email adapter for testing."""

    def __init__(self, *, healthy: bool = True) -> None:
        self._healthy = healthy
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def health_check(self) -> bool:
        return self._healthy

    @property
    def service_type(self) -> str:
        return "email"


class MockMessagingAdapter:
    """Mock messaging adapter for testing."""

    def __init__(self) -> None:
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def health_check(self) -> bool:
        return True

    @property
    def service_type(self) -> str:
        return "messaging"


class TestExternalServiceAdapterProtocol:
    def test_mock_satisfies_protocol(self) -> None:
        adapter = MockCalendarAdapter()
        assert isinstance(adapter, ExternalServiceAdapter)

    def test_email_satisfies_protocol(self) -> None:
        adapter = MockEmailAdapter()
        assert isinstance(adapter, ExternalServiceAdapter)

    def test_messaging_satisfies_protocol(self) -> None:
        adapter = MockMessagingAdapter()
        assert isinstance(adapter, ExternalServiceAdapter)

    def test_service_type_property(self) -> None:
        assert MockCalendarAdapter().service_type == "calendar"
        assert MockEmailAdapter().service_type == "email"
        assert MockMessagingAdapter().service_type == "messaging"


class TestExternalServiceManagerRegister:
    def test_register_adapter(self) -> None:
        manager = ExternalServiceManager()
        adapter = MockCalendarAdapter()
        manager.register(adapter)
        assert len(manager) == 1
        assert "calendar" in manager.registered_types

    def test_register_multiple(self) -> None:
        manager = ExternalServiceManager()
        manager.register(MockCalendarAdapter())
        manager.register(MockEmailAdapter())
        manager.register(MockMessagingAdapter())
        assert len(manager) == 3
        assert sorted(manager.registered_types) == ["calendar", "email", "messaging"]

    def test_register_overwrites_same_type(self) -> None:
        manager = ExternalServiceManager()
        adapter1 = MockCalendarAdapter(healthy=True)
        adapter2 = MockCalendarAdapter(healthy=False)
        manager.register(adapter1)
        manager.register(adapter2)
        assert len(manager) == 1
        assert manager.get("calendar") is adapter2

    def test_get_registered(self) -> None:
        manager = ExternalServiceManager()
        adapter = MockCalendarAdapter()
        manager.register(adapter)
        assert manager.get("calendar") is adapter

    def test_get_unregistered(self) -> None:
        manager = ExternalServiceManager()
        assert manager.get("calendar") is None

    def test_empty_manager(self) -> None:
        manager = ExternalServiceManager()
        assert len(manager) == 0
        assert manager.registered_types == []


class TestExternalServiceManagerLifecycle:
    @pytest.fixture
    def manager_with_adapters(self) -> ExternalServiceManager:
        manager = ExternalServiceManager()
        manager.register(MockCalendarAdapter())
        manager.register(MockEmailAdapter())
        return manager

    async def test_start_all_connects(self, manager_with_adapters: ExternalServiceManager) -> None:
        await manager_with_adapters.start_all()
        cal = manager_with_adapters.get("calendar")
        email = manager_with_adapters.get("email")
        assert cal.connected is True  # type: ignore[union-attr]
        assert email.connected is True  # type: ignore[union-attr]

    async def test_stop_all_disconnects(
        self, manager_with_adapters: ExternalServiceManager
    ) -> None:
        await manager_with_adapters.start_all()
        await manager_with_adapters.stop_all()
        cal = manager_with_adapters.get("calendar")
        assert cal.connected is False  # type: ignore[union-attr]
        assert cal.disconnect_called is True  # type: ignore[union-attr]

    async def test_start_all_handles_connect_failure(self) -> None:
        manager = ExternalServiceManager()
        manager.register(MockCalendarAdapter(fail_connect=True))
        manager.register(MockEmailAdapter())
        # Should not raise — failures are logged
        await manager.start_all()
        # Calendar failed, email succeeded
        assert manager.get_status("calendar") == ServiceStatus.ERROR
        assert manager.get_status("email") == ServiceStatus.CONNECTED

    async def test_start_all_sets_status(
        self, manager_with_adapters: ExternalServiceManager
    ) -> None:
        await manager_with_adapters.start_all()
        assert manager_with_adapters.get_status("calendar") == ServiceStatus.CONNECTED
        assert manager_with_adapters.get_status("email") == ServiceStatus.CONNECTED


class TestExternalServiceManagerHealth:
    async def test_health_check_all_healthy(self) -> None:
        manager = ExternalServiceManager()
        manager.register(MockCalendarAdapter(healthy=True))
        manager.register(MockEmailAdapter(healthy=True))
        result = await manager.health_check_all()
        assert result["calendar"] == ServiceStatus.CONNECTED
        assert result["email"] == ServiceStatus.CONNECTED

    async def test_health_check_all_unhealthy(self) -> None:
        manager = ExternalServiceManager()
        manager.register(MockCalendarAdapter(healthy=False))
        result = await manager.health_check_all()
        assert result["calendar"] == ServiceStatus.ERROR

    async def test_health_check_updates_status(self) -> None:
        manager = ExternalServiceManager()
        adapter = MockCalendarAdapter(healthy=True)
        manager.register(adapter)
        await manager.health_check_all()
        assert manager.get_status("calendar") == ServiceStatus.CONNECTED
        # Simulate unhealthy
        adapter._healthy = False
        await manager.health_check_all()
        assert manager.get_status("calendar") == ServiceStatus.ERROR

    def test_get_status_unregistered(self) -> None:
        manager = ExternalServiceManager()
        assert manager.get_status("unknown") == ServiceStatus.DISABLED

    async def test_health_check_exception_returns_error(self) -> None:
        """Adapter that raises during health_check."""

        class FailingAdapter:
            async def connect(self) -> None:
                pass

            async def disconnect(self) -> None:
                pass

            async def health_check(self) -> bool:
                msg = "Connection lost"
                raise ConnectionError(msg)

            @property
            def service_type(self) -> str:
                return "failing"

        manager = ExternalServiceManager()
        manager.register(FailingAdapter())  # type: ignore[arg-type]
        result = await manager.health_check_all()
        assert result["failing"] == ServiceStatus.ERROR
