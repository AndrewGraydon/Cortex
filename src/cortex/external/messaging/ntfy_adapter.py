"""ntfy messaging adapter — push notifications via ntfy HTTP API.

ntfy (https://ntfy.sh) provides HTTP-based pub/sub notifications.
Messages are POSTed as simple HTTP requests — no SDK required.
Uses httpx (already in deps) for async HTTP.
"""

from __future__ import annotations

import httpx
import structlog

from cortex.external.types import ExternalNotification

logger = structlog.get_logger()


class NtfyMessagingAdapter:
    """ntfy adapter implementing ExternalServiceAdapter protocol.

    Sends push notifications to ntfy topics via HTTP POST.
    """

    def __init__(
        self,
        server: str = "https://ntfy.sh",
        default_topic: str = "cortex",
        access_token: str = "",
    ) -> None:
        self._server = server.rstrip("/")
        self._default_topic = default_topic
        self._access_token = access_token
        self._client: httpx.AsyncClient | None = None
        self._connected = False

    async def connect(self) -> None:
        """Initialize the HTTP client."""
        self._client = httpx.AsyncClient(timeout=10.0)
        self._connected = True
        logger.info("ntfy adapter connected", server=self._server)

    async def disconnect(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._connected = False
        logger.info("ntfy adapter disconnected")

    async def health_check(self) -> bool:
        """Check if the ntfy server is reachable."""
        if not self._connected or self._client is None:
            return False
        try:
            resp = await self._client.get(f"{self._server}/v1/health")
            return resp.status_code == 200
        except Exception:
            logger.exception("ntfy health check failed")
            return False

    @property
    def service_type(self) -> str:
        return "messaging"

    async def send_notification(self, notification: ExternalNotification) -> bool:
        """Send a notification via ntfy HTTP POST.

        Returns True on success, False on failure.
        """
        if self._client is None:
            return False

        topic = notification.topic or self._default_topic
        url = f"{self._server}/{topic}"

        headers: dict[str, str] = {}
        if notification.title:
            headers["Title"] = notification.title
        if notification.priority != 3:
            headers["Priority"] = str(notification.priority)
        if notification.tags:
            headers["Tags"] = ",".join(notification.tags)
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        try:
            resp = await self._client.post(
                url,
                content=notification.message,
                headers=headers,
            )
            if resp.status_code == 200:
                logger.info(
                    "ntfy notification sent",
                    topic=topic,
                    title=notification.title,
                )
                return True
            logger.warning(
                "ntfy notification failed",
                status=resp.status_code,
                body=resp.text[:200],
            )
            return False
        except Exception:
            logger.exception("ntfy send_notification failed")
            return False
