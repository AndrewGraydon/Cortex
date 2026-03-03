"""Permission engine — tier-based access control for actions.

4-tier model (DD-003):
  Tier 0 (SAFE): Auto-approved, no audit logging
  Tier 1 (NORMAL): Auto-approved, audit logged
  Tier 2 (RISKY): Requires user approval via button
  Tier 3 (DANGER): Requires user approval + confirmation reason
"""

from __future__ import annotations

import logging
import time
import uuid

from cortex.security.types import (
    ApprovalStatus,
    AuditEntry,
    PermissionCheck,
    PermissionTier,
)

logger = logging.getLogger(__name__)


class PermissionEngine:
    """Checks and enforces permission tiers for actions.

    Tier 0-1: auto-approved (Tier 1 logged via audit).
    Tier 2-3: delegates to ApprovalManager for button-driven approval.
    """

    def __init__(self, approval_manager: object | None = None) -> None:
        self._approval_manager = approval_manager

    async def check(
        self,
        action_id: str,
        tier: PermissionTier,
        source: str = "voice",
    ) -> PermissionCheck:
        """Check if an action is allowed at the given tier.

        Returns a PermissionCheck with the approval status.
        For Tier 2-3, delegates to the approval manager.
        """
        if tier == PermissionTier.SAFE:
            return PermissionCheck(
                allowed=True,
                status=ApprovalStatus.AUTO_APPROVED,
            )

        if tier == PermissionTier.NORMAL:
            return PermissionCheck(
                allowed=True,
                status=ApprovalStatus.AUTO_APPROVED,
            )

        # Tier 2 and 3 require user approval
        if self._approval_manager is None:
            logger.warning(
                "No approval manager — denying Tier %d action %s",
                tier,
                action_id,
            )
            return PermissionCheck(
                allowed=False,
                status=ApprovalStatus.TIMEOUT,
                reason="No approval manager configured",
            )

        # Delegate to approval manager
        return await self._request_approval(action_id, tier, source)

    async def _request_approval(
        self,
        action_id: str,
        tier: PermissionTier,
        source: str,
    ) -> PermissionCheck:
        """Request approval from the user via the approval manager."""
        from cortex.security.approval import ApprovalManager
        from cortex.security.types import ApprovalRequest

        if not isinstance(self._approval_manager, ApprovalManager):
            return PermissionCheck(
                allowed=False,
                status=ApprovalStatus.TIMEOUT,
                reason="Invalid approval manager",
            )

        request = ApprovalRequest(
            request_id=uuid.uuid4().hex[:12],
            action_id=action_id,
            action_description=f"Execute {action_id}",
            permission_tier=tier,
            timeout_seconds=self._approval_manager.timeout_seconds,
        )

        result = await self._approval_manager.request_approval(request)

        if result == ApprovalStatus.USER_APPROVED:
            return PermissionCheck(allowed=True, status=result)
        return PermissionCheck(
            allowed=False,
            status=result,
            reason=f"Action {action_id} {result.value}",
        )

    def make_audit_entry(
        self,
        action_type: str,
        action_id: str,
        check: PermissionCheck,
        tier: PermissionTier,
        source: str = "voice",
        parameters: dict[str, object] | None = None,
        duration_ms: float = 0.0,
        error_message: str | None = None,
    ) -> AuditEntry:
        """Create an audit entry from a permission check result."""
        return AuditEntry(
            id=uuid.uuid4().hex[:16],
            timestamp=time.time(),
            action_type=action_type,
            action_id=action_id,
            parameters=parameters,
            permission_tier=tier,
            approval_status=check.status.value,
            result="success" if check.allowed else "denied",
            source=source,
            duration_ms=duration_ms,
            error_message=error_message,
        )
