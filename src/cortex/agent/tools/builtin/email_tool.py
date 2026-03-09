"""Email tools — query inbox and send messages. Tier 0 (query) / Tier 2 (send).

Wired to email adapter backends. Falls back to stub responses
if no backend is configured.
"""

from __future__ import annotations

import logging
from typing import Any

from cortex.agent.types import ToolResult

logger = logging.getLogger(__name__)

# Module-level backends — set via set_email_backend()
_imap_adapter: Any = None
_smtp_adapter: Any = None


def set_email_backend(imap: Any = None, smtp: Any = None) -> None:
    """Wire the email tools to real or mock adapters."""
    global _imap_adapter, _smtp_adapter  # noqa: PLW0603
    _imap_adapter = imap
    _smtp_adapter = smtp


def get_email_backend() -> tuple[Any, Any]:
    """Get the current email backends (for testing)."""
    return _imap_adapter, _smtp_adapter


class EmailQueryTool:
    """Query inbox for recent/unread emails. Tier 0 (safe, read-only)."""

    @property
    def name(self) -> str:
        return "email_query"

    @property
    def description(self) -> str:
        return "Check inbox for recent or unread emails"

    @property
    def permission_tier(self) -> int:
        return 0

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "email_query",
            "description": "Check inbox for recent or unread emails",
            "parameters": {
                "type": "object",
                "properties": {
                    "unread_only": {
                        "type": "boolean",
                        "description": "Only show unread messages (default false)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum messages to return (default 5)",
                    },
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if _imap_adapter is None:
            return ToolResult(
                tool_name="email_query",
                success=True,
                data=[],
                display_text="Email is not configured.",
            )

        unread_only = arguments.get("unread_only", False)
        limit = arguments.get("limit", 5)
        if not isinstance(limit, int) or limit < 1:
            limit = 5
        limit = min(limit, 20)

        try:
            messages = await _imap_adapter.list_messages(
                limit=limit,
                unread_only=unread_only,
            )

            if not messages:
                qualifier = "unread " if unread_only else ""
                return ToolResult(
                    tool_name="email_query",
                    success=True,
                    data=[],
                    display_text=f"No {qualifier}emails.",
                )

            data = [
                {
                    "message_id": m.message_id,
                    "subject": m.subject,
                    "sender": m.sender,
                    "date": m.date.isoformat(),
                    "preview": m.preview,
                    "is_read": m.is_read,
                }
                for m in messages
            ]

            # Build display text
            if len(messages) == 1:
                display = f"You have 1 email: {messages[0].format_display()}."
            else:
                items = [m.format_display() for m in messages[:3]]
                display = f"You have {len(messages)} emails. " + ". ".join(items) + "."

            return ToolResult(
                tool_name="email_query",
                success=True,
                data=data,
                display_text=display,
            )
        except Exception as e:
            logger.exception("Email query failed")
            return ToolResult(
                tool_name="email_query",
                success=False,
                error=str(e),
            )


class EmailSendTool:
    """Send an email. Tier 2 (risky — requires approval)."""

    @property
    def name(self) -> str:
        return "email_send"

    @property
    def description(self) -> str:
        return "Send an email message"

    @property
    def permission_tier(self) -> int:
        return 2

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "email_send",
            "description": "Send an email message",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line",
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body text",
                    },
                },
                "required": ["to", "subject", "body"],
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        # Check both SMTP adapter and IMAP adapter (which might provide send)
        adapter = _smtp_adapter or _imap_adapter
        if adapter is None or not hasattr(adapter, "send_message"):
            return ToolResult(
                tool_name="email_send",
                success=False,
                error="Email sending is not configured.",
            )

        to = arguments.get("to", "").strip()
        subject = arguments.get("subject", "").strip()
        body = arguments.get("body", "").strip()

        if not to:
            return ToolResult(
                tool_name="email_send",
                success=False,
                error="Recipient address is required.",
            )
        if not subject:
            return ToolResult(
                tool_name="email_send",
                success=False,
                error="Subject is required.",
            )
        if not body:
            return ToolResult(
                tool_name="email_send",
                success=False,
                error="Message body is required.",
            )

        try:
            success = await adapter.send_message(to=to, subject=subject, body=body)
            if success:
                return ToolResult(
                    tool_name="email_send",
                    success=True,
                    data={"to": to, "subject": subject},
                    display_text=f"Email sent to {to}: {subject}.",
                )
            return ToolResult(
                tool_name="email_send",
                success=False,
                error="Failed to send email.",
            )
        except Exception as e:
            logger.exception("Email send failed")
            return ToolResult(
                tool_name="email_send",
                success=False,
                error=str(e),
            )
