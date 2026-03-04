"""Tests for Milestone 3a.2 — authentication middleware and login/logout flows."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from cortex.config import CortexConfig, WebConfig
from cortex.web.app import create_app
from cortex.web.auth import AuthService
from cortex.web.middleware import SESSION_COOKIE_NAME

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def password_hash() -> str:
    return AuthService.hash_password("testpass123")


@pytest.fixture
def auth_db_path() -> str:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path  # type: ignore[misc]
    os.unlink(path)


@pytest.fixture
def config(password_hash: str) -> CortexConfig:
    return CortexConfig(web=WebConfig(password_hash=password_hash))


def _add_test_post_route(application):  # type: ignore[no-untyped-def]
    """Add a test POST endpoint for CSRF validation testing."""

    @application.post("/test-csrf")
    async def test_csrf_endpoint(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})


@pytest.fixture
def app_with_auth(config: CortexConfig, auth_db_path: str) -> TestClient:
    """App with authentication enabled and AuthService wired."""
    auth = AuthService(
        db_path=auth_db_path,
        password_hash=config.web.password_hash,
        session_timeout_local=config.web.session_timeout_local,
        session_timeout_remote=config.web.session_timeout_remote,
    )
    application = create_app(config=config, enable_auth=True, auth=auth)
    _add_test_post_route(application)
    with TestClient(application) as client:
        yield client


@pytest.fixture
def app_no_auth(config: CortexConfig) -> TestClient:
    """App with authentication middleware disabled (for template tests)."""
    application = create_app(config=config, enable_auth=False)
    with TestClient(application) as client:
        yield client


def _login(client: TestClient, password: str = "testpass123") -> TestClient:
    """Helper to log in and return the client with session cookie."""
    client.post("/login", data={"password": password, "next": "/"})
    return client


# ---------------------------------------------------------------------------
# Middleware redirect tests
# ---------------------------------------------------------------------------


class TestMiddlewareRedirects:
    """Unauthenticated requests should redirect to /login."""

    def test_index_redirects_without_session(self, app_with_auth: TestClient) -> None:
        response = app_with_auth.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert "/login" in response.headers["location"]

    def test_health_accessible_without_session(self, app_with_auth: TestClient) -> None:
        response = app_with_auth.get("/api/health")
        assert response.status_code == 200

    def test_login_page_accessible_without_session(self, app_with_auth: TestClient) -> None:
        response = app_with_auth.get("/login")
        assert response.status_code == 200

    def test_static_accessible_without_session(self, app_with_auth: TestClient) -> None:
        response = app_with_auth.get("/static/css/cortex.css")
        assert response.status_code == 200

    def test_redirect_preserves_next_url(self, app_with_auth: TestClient) -> None:
        response = app_with_auth.get("/dashboard", follow_redirects=False)
        assert response.status_code == 303
        assert "next=/dashboard" in response.headers["location"]


# ---------------------------------------------------------------------------
# Login flow tests
# ---------------------------------------------------------------------------


class TestLoginFlow:
    """Tests for the login form and session creation."""

    def test_login_page_renders(self, app_with_auth: TestClient) -> None:
        response = app_with_auth.get("/login")
        assert response.status_code == 200
        assert "Password" in response.text
        assert "Sign In" in response.text

    def test_login_correct_password_sets_cookie(self, app_with_auth: TestClient) -> None:
        response = app_with_auth.post(
            "/login",
            data={"password": "testpass123", "next": "/"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert SESSION_COOKIE_NAME in response.cookies

    def test_login_wrong_password_shows_error(self, app_with_auth: TestClient) -> None:
        response = app_with_auth.post(
            "/login",
            data={"password": "wrongpass", "next": "/"},
        )
        assert response.status_code == 401
        assert "Invalid password" in response.text

    def test_login_redirects_to_next(self, app_with_auth: TestClient) -> None:
        response = app_with_auth.post(
            "/login",
            data={"password": "testpass123", "next": "/dashboard"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/dashboard"

    def test_authenticated_access_after_login(self, app_with_auth: TestClient) -> None:
        _login(app_with_auth)
        response = app_with_auth.get("/")
        assert response.status_code == 200
        assert "Cortex" in response.text


# ---------------------------------------------------------------------------
# Logout flow tests
# ---------------------------------------------------------------------------


class TestLogoutFlow:
    """Tests for logout and session deletion."""

    def test_logout_clears_cookie(self, app_with_auth: TestClient) -> None:
        _login(app_with_auth)
        response = app_with_auth.post("/logout", follow_redirects=False)
        assert response.status_code == 303
        # Cookie should be deleted
        cookie_header = response.headers.get("set-cookie", "")
        assert SESSION_COOKIE_NAME in cookie_header

    def test_logout_redirects_to_login(self, app_with_auth: TestClient) -> None:
        _login(app_with_auth)
        response = app_with_auth.post("/logout", follow_redirects=False)
        assert response.headers["location"] == "/login"

    def test_access_denied_after_logout(self, app_with_auth: TestClient) -> None:
        _login(app_with_auth)
        app_with_auth.post("/logout")
        # Clear cookies manually since TestClient may hold old ones
        app_with_auth.cookies.clear()
        response = app_with_auth.get("/", follow_redirects=False)
        assert response.status_code == 303


# ---------------------------------------------------------------------------
# CSRF validation tests
# ---------------------------------------------------------------------------


class TestCsrfValidation:
    """Tests for CSRF token enforcement on POST/PUT/DELETE."""

    def test_post_without_csrf_rejected(self, app_with_auth: TestClient) -> None:
        _login(app_with_auth)
        response = app_with_auth.post("/test-csrf")
        assert response.status_code == 403
        assert "CSRF" in response.text

    def test_post_with_valid_csrf_accepted(self, app_with_auth: TestClient) -> None:
        _login(app_with_auth)
        # Get the session cookie to derive CSRF token
        session_id = app_with_auth.cookies.get(SESSION_COOKIE_NAME)
        assert session_id is not None
        csrf_token = AuthService.generate_csrf_token(session_id)
        response = app_with_auth.post(
            "/test-csrf",
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 200

    def test_post_with_wrong_csrf_rejected(self, app_with_auth: TestClient) -> None:
        _login(app_with_auth)
        response = app_with_auth.post(
            "/test-csrf",
            headers={"X-CSRF-Token": "wrong-token"},
        )
        assert response.status_code == 403

    def test_logout_exempt_from_csrf(self, app_with_auth: TestClient) -> None:
        _login(app_with_auth)
        response = app_with_auth.post("/logout", follow_redirects=False)
        assert response.status_code == 303


# ---------------------------------------------------------------------------
# Session invalidation tests
# ---------------------------------------------------------------------------


class TestSessionInvalidation:
    """Tests for invalid/expired session handling."""

    def test_invalid_session_cookie_redirects(self, app_with_auth: TestClient) -> None:
        app_with_auth.cookies.set(SESSION_COOKIE_NAME, "nonexistent-session-id")
        response = app_with_auth.get("/", follow_redirects=False)
        assert response.status_code == 303


# ---------------------------------------------------------------------------
# Login page template tests
# ---------------------------------------------------------------------------


class TestLoginTemplate:
    """Tests for the login page template."""

    def test_login_has_form(self, app_with_auth: TestClient) -> None:
        response = app_with_auth.get("/login")
        assert '<form method="post"' in response.text

    def test_login_has_password_field(self, app_with_auth: TestClient) -> None:
        response = app_with_auth.get("/login")
        assert 'type="password"' in response.text

    def test_login_has_submit_button(self, app_with_auth: TestClient) -> None:
        response = app_with_auth.get("/login")
        assert 'type="submit"' in response.text

    def test_login_preserves_next_param(self, app_with_auth: TestClient) -> None:
        response = app_with_auth.get("/login?next=/dashboard")
        assert "/dashboard" in response.text
