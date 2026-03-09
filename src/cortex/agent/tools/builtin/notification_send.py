"""External notification tool — send push notifications via ntfy. Tier 1 (normal, logged)."""

from __future__ import annotations

import logging
from typing import Any

from cortex.agent.types import ToolResult
from cortex.external.types import ExternalNotification

logger = logging.getLogger(__name__)

# Module-level backend — set via set_notification_backend()
_adapter: Any = None


def set_notification_backend(adapter: Any) -> None:
    """Wire the notification tool to a messaging adapter."""
    global _adapter  # noqa: PLW0603
    _adapter = adapter


def get_notification_backend() -> Any:
    """Get the current notification backend (for testing)."""
    return _adapter


class NotificationSendExternalTool:
    """Send a push notification to an external service. Tier 1 (normal, logged)."""

    @property
    def name(self) -> str:
        return "notification_send_external"

    @property
    def description(self) -> str:
        return "Send a push notification to your phone or other devices"

    @property
    def permission_tier(self) -> int:
        return 1

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "notification_send_external",
            "description": "Send a push notification to your phone or other devices",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Notification message text",
                    },
                    "title": {
                        "type": "string",
                        "description": "Notification title (optional)",
                    },
                    "priority": {
                        "type": "integer",
                        "description": "Priority 1-5 (1=min, 3=default, 5=max)",
                    },
                },
                "required": ["message"],
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if _adapter is None:
            return ToolResult(
                tool_name="notification_send_external",
                success=False,
                error="External notifications are not configured.",
            )

        message = arguments.get("message", "").strip()
        if not message:
            return ToolResult(
                tool_name="notification_send_external",
                success=False,
                error="Message text is required.",
            )

        title = arguments.get("title", "")
        priority = arguments.get("priority", 3)
        if not isinstance(priority, int) or priority < 1 or priority > 5:
            priority = 3

        notification = ExternalNotification(
            message=message,
            title=title,
            priority=priority,
        )

        try:
            success = await _adapter.send_notification(notification)
            if success:
                return ToolResult(
                    tool_name="notification_send_external",
                    success=True,
                    data={"message": message, "title": title},
                    display_text=f"Notification sent: {message[:50]}.",
                )
            return ToolResult(
                tool_name="notification_send_external",
                success=False,
                error="Failed to send notification.",
            )
        except Exception as e:
            logger.exception("Notification send failed")
            return ToolResult(
                tool_name="notification_send_external",
                success=False,
                error=str(e),
            )
