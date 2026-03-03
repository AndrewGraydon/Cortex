"""Security data types — permissions, audit, approvals."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class PermissionTier(enum.IntEnum):
    """4-tier permission model (DD-003).

    Tier 0: Safe — always allowed, no logging
    Tier 1: Normal — allowed, logged with audit trail
    Tier 2: Risky — requires explicit user approval
    Tier 3: Danger — requires confirmation + reason
    """

    SAFE = 0
    NORMAL = 1
    RISKY = 2
    DANGER = 3


class ApprovalStatus(enum.Enum):
    """Status of a permission approval request."""

    PENDING = "pending"
    AUTO_APPROVED = "auto"
    USER_APPROVED = "approved"
    USER_DENIED = "denied"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class PermissionCheck:
    """Result of a permission check."""

    allowed: bool
    status: ApprovalStatus
    reason: str = ""


@dataclass(frozen=True)
class ApprovalRequest:
    """A pending approval request shown to the user."""

    request_id: str
    action_id: str
    action_description: str
    permission_tier: PermissionTier
    parameters: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 60.0


@dataclass
class AuditEntry:
    """A single audit log entry."""

    id: str
    timestamp: float
    action_type: str
    action_id: str | None = None
    parameters: dict[str, Any] | None = None
    permission_tier: int = 0
    approval_status: str = "auto"
    result: str = "success"  # success, failure, error
    source: str = "voice"  # voice, scheduled, agent
    duration_ms: float = 0.0
    error_message: str | None = None
