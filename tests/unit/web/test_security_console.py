"""Tests for Milestone 3a.7 — security console page and audit API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from cortex.config import CortexConfig
from cortex.web.app import create_app


def _make_app(**overrides: object) -> TestClient:
    app = create_app(config=CortexConfig(), enable_auth=False, **overrides)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Security page tests
# ---------------------------------------------------------------------------


class TestSecurityPage:
    """Tests for GET /security page."""

    def test_page_returns_200(self) -> None:
        with _make_app() as client:
            response = client.get("/security")
            assert response.status_code == 200

    def test_page_has_title(self) -> None:
        with _make_app() as client:
            response = client.get("/security")
            assert "Security" in response.text

    def test_page_has_permission_tiers(self) -> None:
        with _make_app() as client:
            response = client.get("/security")
            assert "permission-tiers" in response.text

    def test_page_has_audit_table(self) -> None:
        with _make_app() as client:
            response = client.get("/security")
            assert "audit-table" in response.text

    def test_page_has_pagination(self) -> None:
        with _make_app() as client:
            response = client.get("/security")
            assert "audit-pagination" in response.text

    def test_page_has_filters(self) -> None:
        with _make_app() as client:
            response = client.get("/security")
            assert "audit-filters" in response.text


# ---------------------------------------------------------------------------
# Audit API tests
# ---------------------------------------------------------------------------


class TestAuditAPI:
    """Tests for GET /api/security/audit."""

    def test_returns_200(self) -> None:
        with _make_app() as client:
            response = client.get("/api/security/audit")
            assert response.status_code == 200

    def test_empty_without_audit_log(self) -> None:
        with _make_app() as client:
            data = client.get("/api/security/audit").json()
            assert data["entries"] == []
            assert data["total"] == 0

    def test_pagination_params(self) -> None:
        with _make_app() as client:
            data = client.get("/api/security/audit?limit=10&offset=5").json()
            assert data["limit"] == 10
            assert data["offset"] == 5

    async def test_with_audit_entries(self) -> None:
        """Test audit API returns entries from a real audit log."""
        import tempfile

        from cortex.security.audit import SqliteAuditLog
        from cortex.security.types import AuditEntry

        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            audit = SqliteAuditLog(db_path=f.name)
            await audit.start()
            await audit.log(
                AuditEntry(
                    id="test-001",
                    timestamp=1700000000.0,
                    action_type="tool_call",
                    action_id="get_time",
                    permission_tier=0,
                    approval_status="auto",
                    result="success",
                    source="voice",
                    duration_ms=42.5,
                )
            )
            await audit.log(
                AuditEntry(
                    id="test-002",
                    timestamp=1700000001.0,
                    action_type="tool_call",
                    action_id="set_timer",
                    permission_tier=1,
                    approval_status="approved",
                    result="success",
                    source="web",
                    duration_ms=100.0,
                )
            )

            with _make_app(audit_log=audit) as client:
                data = client.get("/api/security/audit").json()
                assert len(data["entries"]) == 2
                assert data["total"] == 2
                # Most recent first
                assert data["entries"][0]["action_id"] == "set_timer"
                assert data["entries"][1]["action_id"] == "get_time"

            await audit.stop()

    async def test_pagination_offset(self) -> None:
        """Test offset-based pagination."""
        import tempfile

        from cortex.security.audit import SqliteAuditLog
        from cortex.security.types import AuditEntry

        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            audit = SqliteAuditLog(db_path=f.name)
            await audit.start()
            for i in range(5):
                await audit.log(
                    AuditEntry(
                        id=f"test-{i:03d}",
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

            with _make_app(audit_log=audit) as client:
                # Get page 2 (offset=2, limit=2)
                data = client.get(
                    "/api/security/audit?limit=2&offset=2"
                ).json()
                assert len(data["entries"]) == 2
                assert data["total"] == 5

            await audit.stop()


# ---------------------------------------------------------------------------
# Permissions API tests
# ---------------------------------------------------------------------------


class TestPermissionsAPI:
    """Tests for GET /api/security/permissions."""

    def test_returns_200(self) -> None:
        with _make_app() as client:
            response = client.get("/api/security/permissions")
            assert response.status_code == 200

    def test_returns_four_tiers(self) -> None:
        with _make_app() as client:
            data = client.get("/api/security/permissions").json()
            assert len(data["tiers"]) == 4

    def test_tier_fields(self) -> None:
        with _make_app() as client:
            tiers = client.get("/api/security/permissions").json()["tiers"]
            for tier in tiers:
                assert "tier" in tier
                assert "name" in tier
                assert "description" in tier
