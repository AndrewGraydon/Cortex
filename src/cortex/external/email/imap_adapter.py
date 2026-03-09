"""IMAP email adapter — read emails via stdlib imaplib."""

from __future__ import annotations

import email
import email.utils
import imaplib
import logging
import os
from datetime import UTC, datetime
from email.header import decode_header
from typing import Any

from cortex.external.types import EmailMessage

logger = logging.getLogger(__name__)


class IMAPEmailAdapter:
    """IMAP adapter implementing ExternalServiceAdapter protocol.

    Reads email via stdlib imaplib. Password from IMAP_PASSWORD env var.
    Combined with SMTPEmailAdapter for full email service.
    """

    def __init__(
        self,
        server: str,
        username: str = "",
        port: int = 993,
        use_ssl: bool = True,
    ) -> None:
        self._server = server
        self._username = username
        self._port = port
        self._use_ssl = use_ssl
        self._connection: imaplib.IMAP4_SSL | imaplib.IMAP4 | None = None
        self._connected = False

    async def connect(self) -> None:
        """Connect to the IMAP server."""
        password = os.environ.get("IMAP_PASSWORD", "")
        try:
            if self._use_ssl:
                self._connection = imaplib.IMAP4_SSL(self._server, self._port)
            else:
                self._connection = imaplib.IMAP4(self._server, self._port)
            self._connection.login(self._username, password)
            self._connected = True
            logger.info("IMAP connected to %s", self._server)
        except Exception:
            self._connected = False
            logger.exception("IMAP connection failed")
            raise

    async def disconnect(self) -> None:
        """Disconnect from the IMAP server."""
        if self._connection is not None:
            try:
                self._connection.logout()
            except Exception:
                logger.exception("IMAP logout failed")
        self._connection = None
        self._connected = False
        logger.info("IMAP disconnected")

    async def health_check(self) -> bool:
        """Check if IMAP connection is alive."""
        if not self._connected or self._connection is None:
            return False
        try:
            self._connection.noop()
            return True
        except Exception:
            return False

    @property
    def service_type(self) -> str:
        return "email"

    async def list_messages(
        self,
        limit: int = 10,
        unread_only: bool = False,
    ) -> list[EmailMessage]:
        """List inbox messages, most recent first."""
        if self._connection is None:
            return []

        try:
            self._connection.select("INBOX", readonly=True)
            criteria = "UNSEEN" if unread_only else "ALL"
            _, data = self._connection.search(None, criteria)
            msg_ids = data[0].split()
            # Take the last N (most recent)
            recent_ids = msg_ids[-limit:] if len(msg_ids) > limit else msg_ids
            recent_ids.reverse()  # Most recent first

            messages: list[EmailMessage] = []
            for msg_id in recent_ids:
                msg = self._fetch_message(msg_id)
                if msg is not None:
                    messages.append(msg)
            return messages
        except Exception:
            logger.exception("IMAP list_messages failed")
            return []

    async def get_unread_count(self) -> int:
        """Return count of unread messages."""
        if self._connection is None:
            return 0
        try:
            self._connection.select("INBOX", readonly=True)
            _, data = self._connection.search(None, "UNSEEN")
            return len(data[0].split()) if data[0] else 0
        except Exception:
            logger.exception("IMAP get_unread_count failed")
            return 0

    def _fetch_message(self, msg_id: bytes) -> EmailMessage | None:
        """Fetch and parse a single message by ID."""
        if self._connection is None:
            return None
        try:
            fetch_id = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
            _, data = self._connection.fetch(fetch_id, "(RFC822 FLAGS)")
            if not data or data[0] is None:
                return None

            raw: Any = data[0]
            if isinstance(raw, tuple):
                raw_email = raw[1]
            else:
                return None

            msg = email.message_from_bytes(raw_email)

            subject = _decode_header_value(msg.get("Subject", ""))
            sender = _decode_header_value(msg.get("From", ""))
            date_str = msg.get("Date", "")
            message_id = msg.get("Message-ID", "")

            # Parse date
            parsed_date = email.utils.parsedate_to_datetime(date_str) if date_str else None
            msg_date = parsed_date if parsed_date else datetime.now(tz=UTC)

            # Get body preview
            preview = _get_body_preview(msg)

            # Check flags for read status
            flags_data = data[0]
            is_read = b"\\Seen" in (flags_data[0] if isinstance(flags_data, tuple) else b"")

            return EmailMessage(
                message_id=message_id,
                subject=subject,
                sender=sender,
                date=msg_date,
                preview=preview[:200],
                is_read=is_read,
            )
        except Exception:
            logger.exception("Failed to parse email message")
            return None


def _decode_header_value(value: str) -> str:
    """Decode an email header that may be encoded."""
    try:
        parts = decode_header(value)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(part)
        return " ".join(decoded)
    except Exception:
        return value


def _get_body_preview(msg: email.message.Message) -> str:
    """Extract a plain text preview from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    return payload.decode("utf-8", errors="replace").strip()[:200]
    else:
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            return payload.decode("utf-8", errors="replace").strip()[:200]
    return ""
