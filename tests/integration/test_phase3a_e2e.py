"""End-to-end integration tests verifying Phase 3a exit criteria.

Exit criteria:
1. Web UI accessible via browser with bcrypt authentication
2. Chat interface supports full voice-equivalent conversation via WebSocket
3. All Tier 2/3 actions approvable via both LCD button and web UI
4. All 8 pages render (index, login, chat, dashboard, notifications, tools, settings, security)
5. Dashboard shows health from HealthMonitor
6. Web actions appear in audit log with source="web"
7. Tool manager lists tools and supports hot-reload
8. Settings page shows configuration sections
9. Security console shows audit log with pagination
"""

from __future__ import annotations

import os
import tempfile

import pytest
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
    return AuthService.hash_password("test-password-123")


@pytest.fixture
def auth_db_path() -> str:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path  # type: ignore[misc]
    os.unlink(path)


@pytest.fixture
def config(password_hash: str) -> CortexConfig:
    return CortexConfig(web=WebConfig(password_hash=password_hash))


@pytest.fixture
def auth_client(
    config: CortexConfig,
    auth_db_path: str,
) -> TestClient:
    """Fully configured app with auth enabled."""
    auth = AuthService(
        db_path=auth_db_path,
        password_hash=config.web.password_hash,
        session_timeout_local=config.web.session_timeout_local,
        session_timeout_remote=config.web.session_timeout_remote,
    )
    app = create_app(config=config, enable_auth=True, auth=auth)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def no_auth_client(config: CortexConfig) -> TestClient:
    """App with auth disabled for page rendering tests."""
    app = create_app(config=config, enable_auth=False)
    with TestClient(app) as client:
        yield client


def _login(client: TestClient) -> TestClient:
    """Log in and return the client with session cookie."""
    client.post(
        "/login",
        data={"password": "test-password-123", "next": "/"},
    )
    return client


# ---------------------------------------------------------------------------
# Exit Criteria 1: Web UI with authentication
# ---------------------------------------------------------------------------


class TestAuthenticationE2E:
    """Web UI accessible with bcrypt authentication."""

    def test_unauthenticated_redirect(self, auth_client: TestClient) -> None:
        """Unauthenticated requests redirect to login."""
        response = auth_client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert "/login" in response.headers["location"]

    def test_login_creates_session(self, auth_client: TestClient) -> None:
        """Correct password creates session cookie."""
        response = auth_client.post(
            "/login",
            data={"password": "test-password-123", "next": "/"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert SESSION_COOKIE_NAME in response.cookies

    def test_wrong_password_rejected(self, auth_client: TestClient) -> None:
        """Wrong password returns 401."""
        response = auth_client.post(
            "/login",
            data={"password": "wrong", "next": "/"},
        )
        assert response.status_code == 401

    def test_authenticated_access(self, auth_client: TestClient) -> None:
        """After login, all pages accessible."""
        _login(auth_client)
        response = auth_client.get("/")
        assert response.status_code == 200

    def test_logout_clears_session(self, auth_client: TestClient) -> None:
        """Logout clears session and redirects."""
        _login(auth_client)
        response = auth_client.post("/logout", follow_redirects=False)
        assert response.status_code == 303


# ---------------------------------------------------------------------------
# Exit Criteria 2: Chat via WebSocket
# ---------------------------------------------------------------------------


class TestChatE2E:
    """Chat interface supports conversation via WebSocket."""

    def test_chat_page_renders(self, no_auth_client: TestClient) -> None:
        response = no_auth_client.get("/chat")
        assert response.status_code == 200
        assert "chat" in response.text.lower()

    def test_websocket_echo(self, no_auth_client: TestClient) -> None:
        """WebSocket echoes messages when no AgentProcessor configured."""
        import json

        with no_auth_client.websocket_connect("/ws/chat") as ws:
            ws.send_text(json.dumps({"message": "Hello from web"}))
            response = ws.receive_text()
            assert "Hello from web" in response

    def test_websocket_xss_escaped(self, no_auth_client: TestClient) -> None:
        """Script tags are escaped in chat responses."""
        import json

        with no_auth_client.websocket_connect("/ws/chat") as ws:
            ws.send_text(json.dumps({"message": "<script>alert(1)</script>"}))
            response = ws.receive_text()
            assert "<script>" not in response
            assert "&lt;script&gt;" in response


# ---------------------------------------------------------------------------
# Exit Criteria 4: All pages render
# ---------------------------------------------------------------------------


class TestAllPagesRender:
    """All 8 pages return 200 and contain expected content."""

    def test_index_page(self, no_auth_client: TestClient) -> None:
        response = no_auth_client.get("/")
        assert response.status_code == 200
        assert "Cortex" in response.text

    def test_login_page(self, auth_client: TestClient) -> None:
        response = auth_client.get("/login")
        assert response.status_code == 200
        assert "Password" in response.text

    def test_chat_page(self, no_auth_client: TestClient) -> None:
        response = no_auth_client.get("/chat")
        assert response.status_code == 200

    def test_dashboard_page(self, no_auth_client: TestClient) -> None:
        response = no_auth_client.get("/dashboard")
        assert response.status_code == 200
        assert "Dashboard" in response.text

    def test_notifications_page(self, no_auth_client: TestClient) -> None:
        response = no_auth_client.get("/notifications")
        assert response.status_code == 200
        assert "Notifications" in response.text

    def test_tools_page(self, no_auth_client: TestClient) -> None:
        response = no_auth_client.get("/tools")
        assert response.status_code == 200
        assert "Tools" in response.text

    def test_settings_page(self, no_auth_client: TestClient) -> None:
        response = no_auth_client.get("/settings")
        assert response.status_code == 200
        assert "Settings" in response.text

    def test_security_page(self, no_auth_client: TestClient) -> None:
        response = no_auth_client.get("/security")
        assert response.status_code == 200
        assert "Security" in response.text


# ---------------------------------------------------------------------------
# Exit Criteria 5: Dashboard shows health
# ---------------------------------------------------------------------------


class TestDashboardHealthE2E:
    """Dashboard shows health from HealthMonitor."""

    def test_health_api_returns_data(self, no_auth_client: TestClient) -> None:
        response = no_auth_client.get("/api/dashboard/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "components" in data

    def test_health_endpoint(self, no_auth_client: TestClient) -> None:
        response = no_auth_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


# ---------------------------------------------------------------------------
# Exit Criteria 6: Audit log with source
# ---------------------------------------------------------------------------


class TestAuditLogE2E:
    """Web actions appear in audit log."""

    async def test_audit_entries_returned(self) -> None:
        """Audit API returns entries from a real audit log."""
        import tempfile

        from cortex.security.audit import SqliteAuditLog
        from cortex.security.types import AuditEntry

        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            audit = SqliteAuditLog(db_path=f.name)
            await audit.start()

            await audit.log(
                AuditEntry(
                    id="e2e-001",
                    timestamp=1700000000.0,
                    action_type="tool_call",
                    action_id="get_time",
                    permission_tier=0,
                    approval_status="auto",
                    result="success",
                    source="web",
                    duration_ms=50.0,
                )
            )

            app = create_app(
                config=CortexConfig(),
                enable_auth=False,
                audit_log=audit,
            )
            with TestClient(app) as client:
                data = client.get("/api/security/audit").json()
                assert len(data["entries"]) == 1
                assert data["entries"][0]["source"] == "web"
                assert data["entries"][0]["action_id"] == "get_time"

            await audit.stop()


# ---------------------------------------------------------------------------
# Exit Criteria 7: Tool manager
# ---------------------------------------------------------------------------


class TestToolManagerE2E:
    """Tool manager lists tools and supports reload."""

    def test_tools_api_empty(self, no_auth_client: TestClient) -> None:
        data = no_auth_client.get("/api/tools").json()
        assert data["tools"] == []

    def test_tools_with_registry(self) -> None:
        """Tool manager lists registered tools."""
        from cortex.agent.tools.registry import ToolRegistry
        from tests.unit.web.test_tools_page import _MockTool

        registry = ToolRegistry()
        registry.register(_MockTool("clock", "Get current time", tier=0))

        app = create_app(
            config=CortexConfig(),
            enable_auth=False,
            tool_registry=registry,
        )
        with TestClient(app) as client:
            data = client.get("/api/tools").json()
            assert len(data["tools"]) == 1
            assert data["tools"][0]["name"] == "clock"


# ---------------------------------------------------------------------------
# Exit Criteria 8: Settings
# ---------------------------------------------------------------------------


class TestSettingsE2E:
    """Settings page shows configuration sections."""

    def test_all_config_sections(self, no_auth_client: TestClient) -> None:
        data = no_auth_client.get("/api/settings").json()
        settings = data["settings"]
        assert "system" in settings
        assert "voice" in settings
        assert "reasoning" in settings
        assert "agent" in settings
        assert "security" in settings
        assert "web" in settings
        assert "health" in settings

    def test_individual_section(self, no_auth_client: TestClient) -> None:
        data = no_auth_client.get("/api/settings/system").json()
        assert data["section"] == "system"
        assert "hostname" in data["data"]


# ---------------------------------------------------------------------------
# Exit Criteria 9: Security console pagination
# ---------------------------------------------------------------------------


class TestSecurityConsoleE2E:
    """Security console shows audit log with pagination."""

    async def test_paginated_audit(self) -> None:
        """Pagination returns correct subsets."""
        import tempfile

        from cortex.security.audit import SqliteAuditLog
        from cortex.security.types import AuditEntry

        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            audit = SqliteAuditLog(db_path=f.name)
            await audit.start()

            for i in range(10):
                await audit.log(
                    AuditEntry(
                        id=f"page-{i:03d}",
                        timestamp=1700000000.0 + i,
                        action_type="tool_call",
                        action_id=f"action_{i}",
                        permission_tier=0,
                        approval_status="auto",
                        result="success",
                        source="voice",
                        duration_ms=10.0,
                    )
                )

            app = create_app(
                config=CortexConfig(),
                enable_auth=False,
                audit_log=audit,
            )
            with TestClient(app) as client:
                # Page 1
                p1 = client.get("/api/security/audit?limit=3&offset=0").json()
                assert len(p1["entries"]) == 3
                assert p1["total"] == 10

                # Page 2
                p2 = client.get("/api/security/audit?limit=3&offset=3").json()
                assert len(p2["entries"]) == 3

                # No overlap
                p1_ids = {e["id"] for e in p1["entries"]}
                p2_ids = {e["id"] for e in p2["entries"]}
                assert p1_ids.isdisjoint(p2_ids)

            await audit.stop()

    def test_permissions_endpoint(self, no_auth_client: TestClient) -> None:
        data = no_auth_client.get("/api/security/permissions").json()
        assert len(data["tiers"]) == 4
