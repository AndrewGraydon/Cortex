"""SMTP email adapter — send emails via stdlib smtplib."""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


class SMTPEmailAdapter:
    """SMTP adapter for sending emails.

    Uses stdlib smtplib. Password from SMTP_PASSWORD env var.
    This is a send-only adapter; pair with IMAPEmailAdapter for reading.
    Does NOT implement ExternalServiceAdapter directly — it's used alongside
    the IMAP adapter which owns the "email" service_type.
    """

    def __init__(
        self,
        server: str,
        port: int = 587,
        use_tls: bool = True,
        username: str = "",
        from_address: str = "",
    ) -> None:
        self._server = server
        self._port = port
        self._use_tls = use_tls
        self._username = username
        self._from_address = from_address or username

    async def send_message(
        self,
        to: str,
        subject: str,
        body: str,
    ) -> bool:
        """Send an email via SMTP. Returns True on success."""
        password = os.environ.get("SMTP_PASSWORD", "")
        msg = MIMEMultipart()
        msg["From"] = self._from_address
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        try:
            if self._use_tls:
                with smtplib.SMTP(self._server, self._port) as smtp:
                    smtp.starttls()
                    smtp.login(self._username, password)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP_SSL(self._server, self._port) as smtp:
                    smtp.login(self._username, password)
                    smtp.send_message(msg)
            logger.info("SMTP sent message to %s: %s", to, subject)
            return True
        except Exception:
            logger.exception("SMTP send_message failed")
            return False
