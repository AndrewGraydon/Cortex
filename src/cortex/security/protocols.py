"""Security protocol interfaces — permissions and audit."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from cortex.security.types import AuditEntry, PermissionCheck, PermissionTier


@runtime_checkable
class PermissionEngine(Protocol):
    """Checks and enforces permission tiers for actions."""

    async def check(
        self,
        action_id: str,
        tier: PermissionTier,
        source: str = "voice",
    ) -> PermissionCheck:
        """Check if an action is allowed at the given tier."""
        ...


@runtime_checkable
class AuditLog(Protocol):
    """Append-only audit log for all action executions."""

    async def log(self, entry: AuditEntry) -> None:
        """Write an audit entry."""
        ...

    async def query(
        self,
        action_type: str | None = None,
        since: float | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Query audit entries with optional filters."""
        ...
