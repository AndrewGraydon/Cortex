"""Action engine — executes tool calls through the permission gate.

Orchestrates: tool call → permission check → execute → audit log.
"""

from __future__ import annotations

import logging
import time

from cortex.agent.tools.registry import ToolRegistry
from cortex.agent.types import ToolCall, ToolResult
from cortex.security.audit import SqliteAuditLog
from cortex.security.permissions import PermissionEngine

logger = logging.getLogger(__name__)


class ActionEngine:
    """Executes tool calls with permission checking and audit logging."""

    def __init__(
        self,
        registry: ToolRegistry,
        permissions: PermissionEngine | None = None,
        audit_log: SqliteAuditLog | None = None,
    ) -> None:
        self._registry = registry
        self._permissions = permissions
        self._audit_log = audit_log

    async def execute(
        self,
        call: ToolCall,
        source: str = "voice",
    ) -> ToolResult:
        """Execute a tool call through the permission gate.

        1. Look up tool in registry
        2. Check permissions for the tool's tier
        3. Execute if allowed
        4. Log to audit trail
        """
        t0 = time.monotonic()

        # Look up tool tier
        tier = self._registry.get_tier(call.name)

        # Check permissions
        if self._permissions:
            check = await self._permissions.check(call.name, tier, source)
            if not check.allowed:
                result = ToolResult(
                    tool_name=call.name,
                    success=False,
                    error=f"Permission denied: {check.reason}",
                )
                await self._log_audit(call, result, tier, source, t0, check.status.value)
                return result

        # Execute tool
        result = await self._registry.execute(call)

        # Log to audit
        approval_status = "auto" if tier.value <= 1 else "approved"
        await self._log_audit(call, result, tier, source, t0, approval_status)

        return result

    async def _log_audit(
        self,
        call: ToolCall,
        result: ToolResult,
        tier: object,
        source: str,
        t0: float,
        approval_status: str,
    ) -> None:
        """Log the action to the audit trail."""
        if self._audit_log is None:
            return

        import uuid

        duration_ms = (time.monotonic() - t0) * 1000
        entry_result = "success" if result.success else "failure"
        if not result.success and result.error and "Permission denied" in result.error:
            entry_result = "denied"

        from cortex.security.types import AuditEntry

        entry = AuditEntry(
            id=uuid.uuid4().hex[:16],
            timestamp=time.time(),
            action_type="tool_call",
            action_id=call.name,
            parameters=call.arguments if call.arguments else None,
            permission_tier=tier.value if hasattr(tier, "value") else 0,
            approval_status=approval_status,
            result=entry_result,
            source=source,
            duration_ms=duration_ms,
            error_message=result.error,
        )
        try:
            await self._audit_log.log(entry)
        except Exception:
            logger.exception("Failed to write audit entry for %s", call.name)
