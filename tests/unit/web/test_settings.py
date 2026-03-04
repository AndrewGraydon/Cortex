"""Tests for Milestone 3a.7 — settings page and API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from cortex.config import CortexConfig
from cortex.web.app import create_app


def _make_app() -> TestClient:
    app = create_app(config=CortexConfig(), enable_auth=False)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Settings page tests
# ---------------------------------------------------------------------------


class TestSettingsPage:
    """Tests for GET /settings page."""

    def test_page_returns_200(self) -> None:
        with _make_app() as client:
            response = client.get("/settings")
            assert response.status_code == 200

    def test_page_has_title(self) -> None:
        with _make_app() as client:
            response = client.get("/settings")
            assert "Settings" in response.text

    def test_page_has_system_section(self) -> None:
        with _make_app() as client:
            response = client.get("/settings")
            assert "section-system" in response.text

    def test_page_has_voice_section(self) -> None:
        with _make_app() as client:
            response = client.get("/settings")
            assert "section-voice" in response.text

    def test_page_has_reasoning_section(self) -> None:
        with _make_app() as client:
            response = client.get("/settings")
            assert "section-reasoning" in response.text

    def test_page_has_web_section(self) -> None:
        with _make_app() as client:
            response = client.get("/settings")
            assert "section-web" in response.text


# ---------------------------------------------------------------------------
# Settings API tests
# ---------------------------------------------------------------------------


class TestSettingsAPI:
    """Tests for GET /api/settings."""

    def test_returns_200(self) -> None:
        with _make_app() as client:
            response = client.get("/api/settings")
            assert response.status_code == 200

    def test_returns_all_sections(self) -> None:
        with _make_app() as client:
            data = client.get("/api/settings").json()
            settings = data["settings"]
            assert "system" in settings
            assert "voice" in settings
            assert "reasoning" in settings
            assert "agent" in settings
            assert "security" in settings
            assert "web" in settings

    def test_system_section_has_hostname(self) -> None:
        with _make_app() as client:
            data = client.get("/api/settings").json()
            assert "hostname" in data["settings"]["system"]

    def test_web_section_has_port(self) -> None:
        with _make_app() as client:
            data = client.get("/api/settings").json()
            assert data["settings"]["web"]["port"] == 8000


# ---------------------------------------------------------------------------
# Settings section API tests
# ---------------------------------------------------------------------------


class TestSettingsSectionAPI:
    """Tests for GET /api/settings/{section}."""

    def test_valid_section(self) -> None:
        with _make_app() as client:
            response = client.get("/api/settings/system")
            assert response.status_code == 200
            data = response.json()
            assert data["section"] == "system"
            assert "hostname" in data["data"]

    def test_voice_section(self) -> None:
        with _make_app() as client:
            data = client.get("/api/settings/voice").json()
            assert data["section"] == "voice"
            assert "activation_mode" in data["data"]

    def test_unknown_section(self) -> None:
        with _make_app() as client:
            data = client.get("/api/settings/nonexistent").json()
            assert "error" in data
