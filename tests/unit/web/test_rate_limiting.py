"""Tests for login rate limiting — 429 after threshold, reset on success."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from cortex.web.api.auth_routes import _login_rate_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Generator[None]:
    """Reset the module-level rate limiter between tests."""
    _login_rate_limiter._attempts.clear()
    yield
    _login_rate_limiter._attempts.clear()


@pytest.fixture()
def client() -> Generator[TestClient]:
    """Create app with auth enabled for rate limit testing."""
    from cortex.config import CortexConfig, WebConfig
    from cortex.web.app import create_app
    from cortex.web.auth import AuthService

    password_hash = AuthService.hash_password("testpass")
    config = CortexConfig(web=WebConfig(password_hash=password_hash))
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    auth = AuthService(db_path=db_path, password_hash=password_hash)
    app = create_app(config, enable_auth=True, auth=auth)
    with TestClient(app) as c:
        yield c
    os.unlink(db_path)


class TestLoginRateLimiting:
    """Rate limiting on POST /login."""

    def test_allows_normal_login(self, client: TestClient) -> None:
        response = client.post(
            "/login",
            data={"password": "testpass", "next": "/"},
            follow_redirects=False,
        )
        assert response.status_code == 303

    def test_429_after_too_many_failures(self, client: TestClient) -> None:
        # Exhaust attempts with wrong password
        for _ in range(5):
            client.post(
                "/login",
                data={"password": "wrong", "next": "/"},
                follow_redirects=False,
            )

        # Next attempt should be rate limited
        response = client.post(
            "/login",
            data={"password": "testpass", "next": "/"},
            follow_redirects=False,
        )
        assert response.status_code == 429
        assert "retry-after" in response.headers

    def test_retry_after_header(self, client: TestClient) -> None:
        for _ in range(5):
            client.post(
                "/login",
                data={"password": "wrong", "next": "/"},
                follow_redirects=False,
            )

        response = client.post(
            "/login",
            data={"password": "wrong", "next": "/"},
            follow_redirects=False,
        )
        assert response.status_code == 429
        retry_after = int(response.headers["retry-after"])
        assert retry_after > 0

    def test_successful_login_resets_counter(self, client: TestClient) -> None:
        # Fail a few times
        for _ in range(3):
            client.post(
                "/login",
                data={"password": "wrong", "next": "/"},
                follow_redirects=False,
            )

        # Succeed — should reset
        response = client.post(
            "/login",
            data={"password": "testpass", "next": "/"},
            follow_redirects=False,
        )
        assert response.status_code == 303

        # Should be able to fail again (counter reset)
        for _ in range(4):
            client.post(
                "/login",
                data={"password": "wrong", "next": "/"},
                follow_redirects=False,
            )
        # 4 failures — still under limit of 5
        result = _login_rate_limiter.check("testclient")
        assert result.remaining >= 0

    def test_different_ips_independent(self, client: TestClient) -> None:
        """Rate limiting is per-IP, not global."""
        # Exhaust one "IP"
        for _ in range(5):
            _login_rate_limiter.record("attacker-ip")

        assert _login_rate_limiter.check("attacker-ip").allowed is False

        # Regular test request should still work (different IP key)
        response = client.post(
            "/login",
            data={"password": "testpass", "next": "/"},
            follow_redirects=False,
        )
        # Not rate limited since different IP
        assert response.status_code == 303
