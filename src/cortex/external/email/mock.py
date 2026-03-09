"""Mock email adapter — in-memory inbox/outbox for testing."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from cortex.external.types import EmailMessage

logger = logging.getLogger(__name__)


class MockEmailAdapter:
    """In-memory email adapter for testing and development.

    Satisfies ExternalServiceAdapter protocol for service_type="email".
    Provides both IMAP (read) and SMTP (send) operations in one adapter.
    """

    def __init__(self) -> None:
        self._inbox: list[EmailMessage] = []
        self._outbox: list[dict[str, str]] = []
        self._connected = False

    async def connect(self) -> None:
        self._connected = True
        logger.info("MockEmailAdapter connected")

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("MockEmailAdapter disconnected")

    async def health_check(self) -> bool:
        return self._connected

    @property
    def service_type(self) -> str:
        return "email"

    # Read operations (IMAP-like)

    async def list_messages(
        self,
        limit: int = 10,
        unread_only: bool = False,
    ) -> list[EmailMessage]:
        """List inbox messages, most recent first."""
        messages = self._inbox
        if unread_only:
            messages = [m for m in messages if not m.is_read]
        messages = sorted(messages, key=lambda m: m.date, reverse=True)
        return messages[:limit]

    async def get_unread_count(self) -> int:
        """Return count of unread messages."""
        return sum(1 for m in self._inbox if not m.is_read)

    # Send operations (SMTP-like)

    async def send_message(
        self,
        to: str,
        subject: str,
        body: str,
    ) -> bool:
        """Send an email message. Returns True on success."""
        self._outbox.append(
            {
                "to": to,
                "subject": subject,
                "body": body,
                "sent_at": datetime.now(tz=UTC).isoformat(),
            }
        )
        logger.info("MockEmailAdapter sent message to %s: %s", to, subject)
        return True

    # Test helpers

    def add_message(self, message: EmailMessage) -> None:
        """Add a message to the inbox (for testing)."""
        self._inbox.append(message)

    def add_sample_messages(self) -> None:
        """Populate inbox with sample messages."""
        now = datetime.now(tz=UTC)
        samples = [
            EmailMessage(
                message_id="mock-msg-1",
                subject="Weekly report",
                sender="reports@example.com",
                date=now,
                preview="Here is the weekly summary...",
                is_read=False,
            ),
            EmailMessage(
                message_id="mock-msg-2",
                subject="Meeting notes",
                sender="team@example.com",
                date=now,
                preview="Notes from today's standup...",
                is_read=True,
            ),
            EmailMessage(
                message_id="mock-msg-3",
                subject="Invoice #4521",
                sender="billing@vendor.com",
                date=now,
                preview="Your invoice is attached...",
                is_read=False,
            ),
        ]
        self._inbox.extend(samples)
