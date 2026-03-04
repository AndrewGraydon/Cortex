"""Tests for Milestone 3a.5 — notification center and WebSocket push."""

from __future__ import annotations

from fastapi.testclient import TestClient

from cortex.config import CortexConfig
from cortex.web.api.notifications import _render_toast
from cortex.web.app import create_app


def _make_app(**overrides: object) -> TestClient:
    app = create_app(config=CortexConfig(), enable_auth=False, **overrides)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Notifications page tests
# ---------------------------------------------------------------------------


class TestNotificationsPage:
    """Tests for GET /notifications page."""

    def test_page_returns_200(self) -> None:
        with _make_app() as client:
            response = client.get("/notifications")
            assert response.status_code == 200

    def test_page_has_title(self) -> None:
        with _make_app() as client:
            response = client.get("/notifications")
            assert "Notifications" in response.text

    def test_page_has_approval_section(self) -> None:
        with _make_app() as client:
            response = client.get("/notifications")
            assert "approval-container" in response.text

    def test_page_has_notification_list(self) -> None:
        with _make_app() as client:
            response = client.get("/notifications")
            assert "notification-items" in response.text

    def test_page_has_toast_container(self) -> None:
        with _make_app() as client:
            response = client.get("/notifications")
            assert "toast-container" in response.text


# ---------------------------------------------------------------------------
# Notifications API tests
# ---------------------------------------------------------------------------


class TestNotificationsAPI:
    """Tests for GET /api/notifications."""

    def test_returns_200(self) -> None:
        with _make_app() as client:
            response = client.get("/api/notifications")
            assert response.status_code == 200

    def test_empty_without_service(self) -> None:
        with _make_app() as client:
            data = client.get("/api/notifications").json()
            assert data["notifications"] == []


# ---------------------------------------------------------------------------
# Notification WebSocket tests
# ---------------------------------------------------------------------------


class TestNotificationWebSocket:
    """Tests for WebSocket /ws/notifications."""

    def test_websocket_connects(self) -> None:
        with _make_app() as client, client.websocket_connect("/ws/notifications") as ws:
            assert ws is not None


# ---------------------------------------------------------------------------
# Toast rendering tests
# ---------------------------------------------------------------------------


class TestToastRendering:
    """Tests for notification toast HTML rendering."""

    def test_info_toast(self) -> None:
        html = _render_toast("Timer Complete", "5 minute timer done", priority=1)
        assert "alert-info" in html
        assert "Timer Complete" in html
        assert "5 minute timer done" in html

    def test_warning_toast(self) -> None:
        html = _render_toast("Reminder", "Call dentist", priority=2)
        assert "alert-warning" in html

    def test_error_toast(self) -> None:
        html = _render_toast("System Alert", "NPU temperature high", priority=3)
        assert "alert-error" in html

    def test_toast_html_escaped(self) -> None:
        html = _render_toast("<script>", "alert('xss')", priority=1)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_toast_has_oob_swap(self) -> None:
        html = _render_toast("Test", "msg", priority=1)
        assert "hx-swap-oob" in html
        assert "toast-container" in html

    def test_toast_has_animation_class(self) -> None:
        html = _render_toast("Test", "msg", priority=1)
        assert "toast-enter" in html
