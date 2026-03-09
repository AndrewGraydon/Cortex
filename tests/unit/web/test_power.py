"""Tests for power web API."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from cortex.config import CortexConfig
from cortex.hal.power.manager import PowerProfileManager
from cortex.hal.power.service import MockPowerService
from cortex.web.app import create_app


@pytest.fixture
def client() -> Generator[TestClient]:
    config = CortexConfig()
    power_service = MockPowerService()
    power_manager = PowerProfileManager()
    app = create_app(
        config=config,
        enable_auth=False,
        power_service=power_service,
        power_manager=power_manager,
    )
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_no_power() -> Generator[TestClient]:
    config = CortexConfig()
    app = create_app(config=config, enable_auth=False)
    with TestClient(app) as c:
        yield c


class TestGetPowerState:
    def test_with_services(self, client: TestClient) -> None:
        resp = client.get("/api/power")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert data["profile"] == "mains"
        assert data["battery_percent"] == 100.0

    def test_without_services(self, client_no_power: TestClient) -> None:
        resp = client_no_power.get("/api/power")
        assert resp.status_code == 200
        assert resp.json()["available"] is False


class TestPowerOverride:
    def test_override_profile(self, client: TestClient) -> None:
        resp = client.post(
            "/api/power/override",
            json={"profile": "low_battery"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "override_set"

    def test_clear_override(self, client: TestClient) -> None:
        resp = client.post(
            "/api/power/override",
            json={"profile": "auto"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "override_cleared"

    def test_invalid_profile(self, client: TestClient) -> None:
        resp = client.post(
            "/api/power/override",
            json={"profile": "invalid"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    def test_no_manager(self, client_no_power: TestClient) -> None:
        resp = client_no_power.post(
            "/api/power/override",
            json={"profile": "mains"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"
