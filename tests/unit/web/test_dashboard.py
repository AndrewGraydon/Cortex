"""Tests for Milestone 3a.4 — dashboard and system health display."""

from __future__ import annotations

from fastapi.testclient import TestClient

from cortex.config import CortexConfig
from cortex.web.app import create_app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_app(**overrides: object) -> TestClient:
    """Create a test app with optional service overrides."""
    app = create_app(config=CortexConfig(), enable_auth=False, **overrides)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Dashboard page tests
# ---------------------------------------------------------------------------


class TestDashboardPage:
    """Tests for GET /dashboard."""

    def test_dashboard_returns_200(self) -> None:
        with _make_app() as client:
            response = client.get("/dashboard")
            assert response.status_code == 200

    def test_dashboard_returns_html(self) -> None:
        with _make_app() as client:
            response = client.get("/dashboard")
            assert "text/html" in response.headers["content-type"]

    def test_dashboard_has_title(self) -> None:
        with _make_app() as client:
            response = client.get("/dashboard")
            assert "Dashboard" in response.text

    def test_dashboard_has_health_section(self) -> None:
        with _make_app() as client:
            response = client.get("/dashboard")
            assert "cpu-load" in response.text
            assert "memory-pct" in response.text
            assert "storage-pct" in response.text

    def test_dashboard_has_timers_section(self) -> None:
        with _make_app() as client:
            response = client.get("/dashboard")
            assert "Active Timers" in response.text

    def test_dashboard_has_recent_section(self) -> None:
        with _make_app() as client:
            response = client.get("/dashboard")
            assert "Recent Actions" in response.text

    def test_dashboard_has_htmx_polling(self) -> None:
        with _make_app() as client:
            response = client.get("/dashboard")
            assert "hx-get" in response.text
            assert "every 10s" in response.text

    def test_dashboard_has_uptime_section(self) -> None:
        with _make_app() as client:
            response = client.get("/dashboard")
            assert "Uptime" in response.text


# ---------------------------------------------------------------------------
# Health API tests
# ---------------------------------------------------------------------------


class TestDashboardHealthAPI:
    """Tests for GET /api/dashboard/health."""

    def test_health_returns_200(self) -> None:
        with _make_app() as client:
            response = client.get("/api/dashboard/health")
            assert response.status_code == 200

    def test_health_returns_json(self) -> None:
        with _make_app() as client:
            response = client.get("/api/dashboard/health")
            data = response.json()
            assert "status" in data
            assert "components" in data

    def test_health_has_cpu(self) -> None:
        with _make_app() as client:
            data = client.get("/api/dashboard/health").json()
            assert "cpu" in data["components"]

    def test_health_has_uptime(self) -> None:
        with _make_app() as client:
            data = client.get("/api/dashboard/health").json()
            assert "uptime_seconds" in data
            assert data["uptime_seconds"] >= 0


# ---------------------------------------------------------------------------
# Timers API tests
# ---------------------------------------------------------------------------


class TestDashboardTimersAPI:
    """Tests for GET /api/dashboard/timers."""

    def test_timers_returns_200(self) -> None:
        with _make_app() as client:
            response = client.get("/api/dashboard/timers")
            assert response.status_code == 200

    def test_timers_empty_without_scheduler(self) -> None:
        with _make_app() as client:
            data = client.get("/api/dashboard/timers").json()
            assert data == {"timers": []}

    def test_timers_returns_list(self) -> None:
        with _make_app() as client:
            data = client.get("/api/dashboard/timers").json()
            assert isinstance(data["timers"], list)


# ---------------------------------------------------------------------------
# Recent actions API tests
# ---------------------------------------------------------------------------


class TestDashboardRecentAPI:
    """Tests for GET /api/dashboard/recent."""

    def test_recent_returns_200(self) -> None:
        with _make_app() as client:
            response = client.get("/api/dashboard/recent")
            assert response.status_code == 200

    def test_recent_empty_without_audit(self) -> None:
        with _make_app() as client:
            data = client.get("/api/dashboard/recent").json()
            assert data == {"actions": []}

    def test_recent_returns_list(self) -> None:
        with _make_app() as client:
            data = client.get("/api/dashboard/recent").json()
            assert isinstance(data["actions"], list)
