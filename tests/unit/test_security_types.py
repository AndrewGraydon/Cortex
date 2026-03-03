"""Tests for security data types — permissions, audit, approvals."""

from __future__ import annotations

import time

from cortex.security.types import (
    ApprovalRequest,
    ApprovalStatus,
    AuditEntry,
    PermissionCheck,
    PermissionTier,
)


class TestPermissionTier:
    def test_all_tiers_exist(self) -> None:
        expected = {0, 1, 2, 3}
        actual = {t.value for t in PermissionTier}
        assert actual == expected

    def test_tier_ordering(self) -> None:
        assert PermissionTier.SAFE < PermissionTier.NORMAL
        assert PermissionTier.NORMAL < PermissionTier.RISKY
        assert PermissionTier.RISKY < PermissionTier.DANGER

    def test_int_enum_comparison(self) -> None:
        assert PermissionTier.SAFE == 0
        assert PermissionTier.DANGER == 3
        assert PermissionTier.RISKY >= 2


class TestApprovalStatus:
    def test_all_statuses_exist(self) -> None:
        expected = {"pending", "auto", "approved", "denied", "timeout"}
        actual = {s.value for s in ApprovalStatus}
        assert actual == expected


class TestPermissionCheck:
    def test_allowed(self) -> None:
        check = PermissionCheck(allowed=True, status=ApprovalStatus.AUTO_APPROVED)
        assert check.allowed
        assert check.status == ApprovalStatus.AUTO_APPROVED
        assert check.reason == ""

    def test_denied(self) -> None:
        check = PermissionCheck(
            allowed=False,
            status=ApprovalStatus.USER_DENIED,
            reason="User denied action",
        )
        assert not check.allowed
        assert check.reason == "User denied action"

    def test_frozen(self) -> None:
        check = PermissionCheck(allowed=True, status=ApprovalStatus.AUTO_APPROVED)
        try:
            check.allowed = False  # type: ignore[misc]
            raise AssertionError("Should be frozen")
        except AttributeError:
            pass


class TestApprovalRequest:
    def test_construction(self) -> None:
        req = ApprovalRequest(
            request_id="req-001",
            action_id="timer_cancel",
            action_description="Cancel timer 'tea'",
            permission_tier=PermissionTier.RISKY,
        )
        assert req.request_id == "req-001"
        assert req.permission_tier == PermissionTier.RISKY
        assert req.timeout_seconds == 60.0
        assert req.parameters == {}

    def test_with_parameters(self) -> None:
        req = ApprovalRequest(
            request_id="req-002",
            action_id="system_reboot",
            action_description="Reboot system",
            permission_tier=PermissionTier.DANGER,
            parameters={"reason": "firmware update"},
            timeout_seconds=30.0,
        )
        assert req.parameters["reason"] == "firmware update"
        assert req.timeout_seconds == 30.0

    def test_frozen(self) -> None:
        req = ApprovalRequest(
            request_id="req-001",
            action_id="test",
            action_description="test",
            permission_tier=PermissionTier.RISKY,
        )
        try:
            req.request_id = "other"  # type: ignore[misc]
            raise AssertionError("Should be frozen")
        except AttributeError:
            pass


class TestAuditEntry:
    def test_defaults(self) -> None:
        entry = AuditEntry(
            id="audit-001",
            timestamp=time.time(),
            action_type="tool_call",
        )
        assert entry.action_id is None
        assert entry.permission_tier == 0
        assert entry.approval_status == "auto"
        assert entry.result == "success"
        assert entry.source == "voice"
        assert entry.duration_ms == 0.0
        assert entry.error_message is None

    def test_full_entry(self) -> None:
        entry = AuditEntry(
            id="audit-002",
            timestamp=1000.0,
            action_type="tool_call",
            action_id="timer_set",
            parameters={"duration": 300},
            permission_tier=1,
            approval_status="auto",
            result="success",
            source="voice",
            duration_ms=42.5,
        )
        assert entry.action_id == "timer_set"
        assert entry.parameters == {"duration": 300}
        assert entry.duration_ms == 42.5

    def test_error_entry(self) -> None:
        entry = AuditEntry(
            id="audit-003",
            timestamp=1000.0,
            action_type="tool_call",
            action_id="timer_set",
            result="error",
            error_message="Database locked",
        )
        assert entry.result == "error"
        assert entry.error_message == "Database locked"
