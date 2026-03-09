"""Tests for network security web API."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from cortex.config import CortexConfig
from cortex.security.network import NetworkSecurityManager
from cortex.web.app import create_app


@pytest.fixture
def client() -> Generator[TestClient]:
    config = CortexConfig()
    net_security = NetworkSecurityManager(enabled=True, default_policy="deny")
    app = create_app(
        config=config,
        enable_auth=False,
        network_security=net_security,
    )
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_no_security() -> Generator[TestClient]:
    config = CortexConfig()
    app = create_app(config=config, enable_auth=False)
    with TestClient(app) as c:
        yield c


class TestGetNetworkRules:
    def test_with_service(self, client: TestClient) -> None:
        resp = client.get("/api/security/network")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["default_policy"] == "deny"

    def test_without_service(self, client_no_security: TestClient) -> None:
        resp = client_no_security.get("/api/security/network")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False


class TestAllowlistAPI:
    def test_add_domain(self, client: TestClient) -> None:
        resp = client.post(
            "/api/security/network/allowlist",
            json={"domain": "example.com"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "added"

    def test_remove_domain(self, client: TestClient) -> None:
        client.post(
            "/api/security/network/allowlist",
            json={"domain": "example.com"},
        )
        resp = client.request(
            "DELETE",
            "/api/security/network/allowlist",
            json={"domain": "example.com"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "removed"

    def test_missing_domain(self, client: TestClient) -> None:
        resp = client.post(
            "/api/security/network/allowlist",
            json={},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    def test_no_service(self, client_no_security: TestClient) -> None:
        resp = client_no_security.post(
            "/api/security/network/allowlist",
            json={"domain": "example.com"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"
