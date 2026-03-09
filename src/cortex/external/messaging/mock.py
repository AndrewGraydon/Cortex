"""Mock messaging adapter — in-memory notification store for testing."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from cortex.external.types import ExternalNotification

logger = logging.getLogger(__name__)


class MockMessagingAdapter:
    """In-memory messaging adapter for testing and development.

    Satisfies ExternalServiceAdapter protocol for service_type="messaging".
    """

    def __init__(self, default_topic: str = "cortex") -> None:
        self._default_topic = default_topic
        self._sent: list[dict[str, object]] = []
        self._connected = False

    async def connect(self) -> None:
        self._connected = True
        logger.info("MockMessagingAdapter connected")

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("MockMessagingAdapter disconnected")

    async def health_check(self) -> bool:
        return self._connected

    @property
    def service_type(self) -> str:
        return "messaging"

    async def send_notification(self, notification: ExternalNotification) -> bool:
        """Send a notification. Returns True on success."""
        topic = notification.topic or self._default_topic
        self._sent.append(
            {
                "topic": topic,
                "message": notification.message,
                "title": notification.title,
                "priority": notification.priority,
                "tags": notification.tags,
                "sent_at": datetime.now(tz=UTC).isoformat(),
            }
        )
        logger.info(
            "MockMessagingAdapter sent notification: %s → %s",
            topic,
            notification.message[:50],
        )
        return True

    @property
    def sent_count(self) -> int:
        """Number of notifications sent (for testing)."""
        return len(self._sent)

    @property
    def sent_messages(self) -> list[dict[str, object]]:
        """All sent notifications (for testing)."""
        return list(self._sent)
