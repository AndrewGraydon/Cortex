"""Tests for Milestone 3a.5 — approval flows and notification center."""

from __future__ import annotations

from fastapi.testclient import TestClient

from cortex.config import CortexConfig
from cortex.security.approval import ApprovalManager
from cortex.security.types import ApprovalRequest, ApprovalStatus, PermissionTier
from cortex.web.app import create_app


def _make_app(**overrides: object) -> TestClient:
    app = create_app(config=CortexConfig(), enable_auth=False, **overrides)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Approval API — no pending request
# ---------------------------------------------------------------------------


class TestApprovalsNoPending:
    """Tests when no approval is pending."""

    def test_pending_returns_null(self) -> None:
        mgr = ApprovalManager()
        with _make_app(approval_manager=mgr) as client:
            data = client.get("/api/approvals/pending").json()
            assert data["pending"] is None

    def test_pending_without_manager(self) -> None:
        with _make_app() as client:
            data = client.get("/api/approvals/pending").json()
            assert data["pending"] is None

    def test_approve_nonexistent_returns_404(self) -> None:
        mgr = ApprovalManager()
        with _make_app(approval_manager=mgr) as client:
            response = client.post("/api/approvals/fake-id/approve")
            assert response.status_code == 404

    def test_deny_nonexistent_returns_404(self) -> None:
        mgr = ApprovalManager()
        with _make_app(approval_manager=mgr) as client:
            response = client.post("/api/approvals/fake-id/deny")
            assert response.status_code == 404

    def test_history_empty(self) -> None:
        mgr = ApprovalManager()
        with _make_app(approval_manager=mgr) as client:
            data = client.get("/api/approvals/history").json()
            assert data["history"] == []


# ---------------------------------------------------------------------------
# Approval API — with pending request
# ---------------------------------------------------------------------------


class TestApprovalsWithPending:
    """Tests when an approval is pending (mocked)."""

    def test_pending_returns_request_details(self) -> None:
        mgr = ApprovalManager()
        # Directly set pending (simulating an in-progress request)
        req = ApprovalRequest(
            request_id="req-001",
            action_id="send_email",
            action_description="Send email to john@example.com",
            permission_tier=PermissionTier.RISKY,
            parameters={"to": "john@example.com"},
        )
        mgr._pending = req  # noqa: SLF001

        with _make_app(approval_manager=mgr) as client:
            data = client.get("/api/approvals/pending").json()
            assert data["pending"] is not None
            assert data["pending"]["request_id"] == "req-001"
            assert data["pending"]["action_id"] == "send_email"
            assert data["pending"]["tier"] == 2
            assert data["pending"]["description"] == "Send email to john@example.com"


# ---------------------------------------------------------------------------
# Approval history
# ---------------------------------------------------------------------------


class TestApprovalHistory:
    """Tests for approval history endpoint."""

    def test_history_contains_past_approvals(self) -> None:
        mgr = ApprovalManager()
        req = ApprovalRequest(
            request_id="req-002",
            action_id="delete_file",
            action_description="Delete /tmp/test.txt",
            permission_tier=PermissionTier.DANGER,
        )
        mgr._history.append((req, ApprovalStatus.USER_APPROVED))  # noqa: SLF001

        with _make_app(approval_manager=mgr) as client:
            data = client.get("/api/approvals/history").json()
            assert len(data["history"]) == 1
            assert data["history"][0]["action_id"] == "delete_file"
            assert data["history"][0]["result"] == "approved"
            assert data["history"][0]["tier"] == 3

    def test_history_without_manager(self) -> None:
        with _make_app() as client:
            data = client.get("/api/approvals/history").json()
            assert data["history"] == []
