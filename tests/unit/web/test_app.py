"""Tests for Milestone 3a.1 — FastAPI app shell, templates, health endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cortex.config import CortexConfig, WebConfig
from cortex.web.app import create_app
from cortex.web.dependencies import ServiceContainer, get_services, init_services

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> CortexConfig:
    """Default config for web tests."""
    return CortexConfig(web=WebConfig(port=8000))


@pytest.fixture
def app(config: CortexConfig) -> TestClient:
    """TestClient with a fully-initialized app (auth disabled for unit tests)."""
    application = create_app(config=config, enable_auth=False)
    with TestClient(application) as client:
        yield client


# ---------------------------------------------------------------------------
# App creation tests
# ---------------------------------------------------------------------------


class TestAppCreation:
    """Tests for create_app() and FastAPI setup."""

    def test_create_app_returns_fastapi(self, config: CortexConfig) -> None:
        from fastapi import FastAPI

        application = create_app(config=config)
        assert isinstance(application, FastAPI)

    def test_app_has_title(self, config: CortexConfig) -> None:
        application = create_app(config=config)
        assert application.title == "Cortex"

    def test_app_has_version(self, config: CortexConfig) -> None:
        application = create_app(config=config)
        assert application.version == "0.1.0"

    def test_app_includes_health_router(self, config: CortexConfig) -> None:
        application = create_app(config=config)
        paths = [route.path for route in application.routes]
        assert "/api/health" in paths

    def test_app_includes_index_route(self, config: CortexConfig) -> None:
        application = create_app(config=config)
        paths = [route.path for route in application.routes]
        assert "/" in paths

    def test_app_mounts_static_files(self, config: CortexConfig) -> None:
        application = create_app(config=config)
        route_names = [
            getattr(route, "name", None) for route in application.routes
        ]
        assert "static" in route_names


# ---------------------------------------------------------------------------
# Index page tests
# ---------------------------------------------------------------------------


class TestIndexPage:
    """Tests for the landing page."""

    def test_index_returns_200(self, app: TestClient) -> None:
        response = app.get("/")
        assert response.status_code == 200

    def test_index_returns_html(self, app: TestClient) -> None:
        response = app.get("/")
        assert "text/html" in response.headers["content-type"]

    def test_index_contains_cortex_title(self, app: TestClient) -> None:
        response = app.get("/")
        assert "Cortex" in response.text

    def test_index_contains_nav_links(self, app: TestClient) -> None:
        response = app.get("/")
        assert "/chat" in response.text
        assert "/dashboard" in response.text

    def test_index_includes_htmx(self, app: TestClient) -> None:
        response = app.get("/")
        assert "htmx.org" in response.text

    def test_index_includes_daisyui(self, app: TestClient) -> None:
        response = app.get("/")
        assert "daisyui" in response.text

    def test_index_includes_custom_css(self, app: TestClient) -> None:
        response = app.get("/")
        assert "/static/css/cortex.css" in response.text

    def test_index_includes_custom_js(self, app: TestClient) -> None:
        response = app.get("/")
        assert "/static/js/cortex.js" in response.text


# ---------------------------------------------------------------------------
# Health endpoint tests
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """Tests for GET /api/health."""

    def test_health_returns_200(self, app: TestClient) -> None:
        response = app.get("/api/health")
        assert response.status_code == 200

    def test_health_returns_json(self, app: TestClient) -> None:
        response = app.get("/api/health")
        assert response.headers["content-type"] == "application/json"

    def test_health_has_status_field(self, app: TestClient) -> None:
        data = app.get("/api/health").json()
        assert "status" in data
        assert data["status"] in ("healthy", "degraded", "unhealthy")

    def test_health_has_uptime(self, app: TestClient) -> None:
        data = app.get("/api/health").json()
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], (int, float))
        assert data["uptime_seconds"] >= 0

    def test_health_has_components(self, app: TestClient) -> None:
        data = app.get("/api/health").json()
        assert "components" in data
        assert isinstance(data["components"], dict)

    def test_health_has_cpu_component(self, app: TestClient) -> None:
        data = app.get("/api/health").json()
        assert "cpu" in data["components"]

    def test_health_has_memory_component(self, app: TestClient) -> None:
        data = app.get("/api/health").json()
        assert "memory" in data["components"]

    def test_health_has_storage_component(self, app: TestClient) -> None:
        data = app.get("/api/health").json()
        assert "storage" in data["components"]

    def test_health_has_models_loaded(self, app: TestClient) -> None:
        data = app.get("/api/health").json()
        assert "models_loaded" in data
        assert isinstance(data["models_loaded"], list)

    def test_health_has_timestamp(self, app: TestClient) -> None:
        data = app.get("/api/health").json()
        assert "timestamp" in data
        assert data["timestamp"] > 0


# ---------------------------------------------------------------------------
# Static file serving tests
# ---------------------------------------------------------------------------


class TestStaticFiles:
    """Tests for static file serving."""

    def test_css_file_accessible(self, app: TestClient) -> None:
        response = app.get("/static/css/cortex.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    def test_js_file_accessible(self, app: TestClient) -> None:
        response = app.get("/static/js/cortex.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]

    def test_css_contains_status_dot(self, app: TestClient) -> None:
        response = app.get("/static/css/cortex.css")
        assert ".status-dot" in response.text

    def test_js_contains_update_function(self, app: TestClient) -> None:
        response = app.get("/static/js/cortex.js")
        assert "updateStatusDot" in response.text

    def test_nonexistent_static_returns_404(self, app: TestClient) -> None:
        response = app.get("/static/nonexistent.txt")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Template rendering tests
# ---------------------------------------------------------------------------


class TestTemplateRendering:
    """Tests for Jinja2 template rendering."""

    def test_base_template_has_html_structure(self, app: TestClient) -> None:
        response = app.get("/")
        text = response.text
        assert "<!DOCTYPE html>" in text
        assert "<html" in text
        assert "</html>" in text

    def test_navbar_rendered_in_index(self, app: TestClient) -> None:
        response = app.get("/")
        assert "navbar" in response.text

    def test_status_indicator_rendered(self, app: TestClient) -> None:
        response = app.get("/")
        assert "status-indicator" in response.text
        assert "status-dot" in response.text

    def test_dark_theme_default(self, app: TestClient) -> None:
        response = app.get("/")
        assert 'data-theme="dark"' in response.text


# ---------------------------------------------------------------------------
# Dependency injection tests
# ---------------------------------------------------------------------------


class TestDependencies:
    """Tests for the service container and dependency injection."""

    def test_init_services_creates_container(self) -> None:
        config = CortexConfig()
        container = init_services(config)
        assert isinstance(container, ServiceContainer)

    def test_container_has_config(self) -> None:
        config = CortexConfig(web=WebConfig(port=9999))
        container = init_services(config)
        assert container.config.web.port == 9999

    def test_container_has_health_monitor(self) -> None:
        from cortex.agent.health import HealthMonitor

        config = CortexConfig()
        container = init_services(config)
        assert isinstance(container.health_monitor, HealthMonitor)

    def test_get_services_returns_container(self) -> None:
        config = CortexConfig()
        init_services(config)
        container = get_services()
        assert isinstance(container, ServiceContainer)

    def test_container_extras_set_get(self) -> None:
        container = ServiceContainer()
        container.set("foo", 42)
        assert container.get("foo") == 42

    def test_container_extras_missing_returns_none(self) -> None:
        container = ServiceContainer()
        assert container.get("nonexistent") is None


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestWebConfig:
    """Tests for the WebConfig model."""

    def test_web_config_defaults(self) -> None:
        config = CortexConfig()
        assert config.web.enabled is True
        assert config.web.host == "0.0.0.0"
        assert config.web.port == 8000
        assert config.web.session_timeout_local == 3600
        assert config.web.session_timeout_remote == 1800
        assert config.web.password_hash == ""

    def test_web_config_custom_values(self) -> None:
        config = CortexConfig(
            web=WebConfig(port=9000, host="127.0.0.1", enabled=False)
        )
        assert config.web.port == 9000
        assert config.web.host == "127.0.0.1"
        assert config.web.enabled is False

    def test_web_config_in_yaml_roundtrip(self) -> None:
        """Config can be created from dict (simulates YAML loading)."""
        data = {"web": {"port": 8080, "session_timeout_local": 7200}}
        config = CortexConfig.model_validate(data)
        assert config.web.port == 8080
        assert config.web.session_timeout_local == 7200
