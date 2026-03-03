"""Notification service — 5-level priority queue with DND support.

Priority levels:
  P0 (silent):      LCD badge only
  P1 (visual):      LCD card + LED amber pulse
  P2 (chime):       LCD + LED + short tone
  P3 (spoken):      LCD + LED + TTS (waits for conversation end)
  P4 (interruptive): Immediate, interrupts everything

During a voice session, P0-P3 are queued. After session ends,
delivered in priority order. P4 always interrupts.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Notification:
    """A notification to be delivered."""

    id: str
    priority: int  # 0-4
    title: str
    body: str = ""
    source: str = "system"  # system, timer, reminder, agent
    created_at: float = 0.0
    delivered: bool = False
    delivered_at: float = 0.0


class NotificationService:
    """5-level priority notification queue with session awareness.

    Args:
        display: Display service for LCD updates.
        audio: Audio service for chime playback.
        dnd_enabled: If True, suppress all non-P4 notifications.
        dnd_start_hour: DND start hour (0-23).
        dnd_end_hour: DND end hour (0-23).
    """

    def __init__(
        self,
        display: Any = None,
        audio: Any = None,
        dnd_enabled: bool = False,
        dnd_start_hour: int = 22,
        dnd_end_hour: int = 7,
    ) -> None:
        self._display = display
        self._audio = audio
        self._dnd_enabled = dnd_enabled
        self._dnd_start = dnd_start_hour
        self._dnd_end = dnd_end_hour
        self._queue: list[Notification] = []
        self._in_session = False
        self._history: list[Notification] = []
        self._on_deliver: Any = None  # Callback for testing

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    @property
    def in_session(self) -> bool:
        return self._in_session

    @in_session.setter
    def in_session(self, value: bool) -> None:
        self._in_session = value

    @property
    def history(self) -> list[Notification]:
        return list(self._history)

    def set_on_deliver(self, callback: Any) -> None:
        """Set a delivery callback (for testing)."""
        self._on_deliver = callback

    async def notify(self, notification: Notification) -> bool:
        """Submit a notification for delivery.

        Returns True if delivered immediately, False if queued.
        """
        if not notification.created_at:
            notification.created_at = time.time()

        # P4 always delivered immediately
        if notification.priority >= 4:
            await self._deliver(notification)
            return True

        # DND mode — suppress non-P4
        if self._is_dnd() and notification.priority < 4:
            logger.debug(
                "DND active — suppressing P%d: %s", notification.priority, notification.title
            )
            self._queue.append(notification)
            return False

        # In voice session — queue P0-P3
        if self._in_session and notification.priority < 4:
            logger.debug("In session — queueing P%d: %s", notification.priority, notification.title)
            self._queue.append(notification)
            return False

        # Deliver immediately
        await self._deliver(notification)
        return True

    async def flush_queue(self) -> list[Notification]:
        """Deliver all queued notifications in priority order.

        Called when voice session ends or DND period ends.
        """
        if not self._queue:
            return []

        # Sort by priority descending (highest first), then by time
        pending = sorted(
            self._queue,
            key=lambda n: (-n.priority, n.created_at),
        )
        self._queue.clear()

        delivered = []
        for notification in pending:
            await self._deliver(notification)
            delivered.append(notification)

        return delivered

    async def _deliver(self, notification: Notification) -> None:
        """Actually deliver a notification via display/audio/TTS."""
        notification.delivered = True
        notification.delivered_at = time.time()
        self._history.append(notification)

        logger.info(
            "Delivering P%d notification: %s",
            notification.priority,
            notification.title,
        )

        if self._on_deliver:
            await self._on_deliver(notification)

        if not (self._display and hasattr(self._display, "show_text")):
            return

        if notification.priority == 0:
            # P0: LCD badge only
            await self._display.show_text(notification.title)
        elif notification.priority >= 4:
            # P4: Interrupt everything
            await self._display.show_text(f"URGENT: {notification.title}")
        else:
            # P1-P3: LCD card with title and body
            await self._display.show_text(f"{notification.title}: {notification.body}")

    def _is_dnd(self) -> bool:
        """Check if current time is within DND hours."""
        if not self._dnd_enabled:
            return False
        from datetime import datetime

        hour = datetime.now().hour
        if self._dnd_start <= self._dnd_end:
            return self._dnd_start <= hour < self._dnd_end
        # Wraps midnight (e.g., 22:00 - 07:00)
        return hour >= self._dnd_start or hour < self._dnd_end

    def clear_queue(self) -> None:
        """Discard all queued notifications."""
        self._queue.clear()

    def set_dnd(self, enabled: bool) -> None:
        """Toggle DND mode."""
        self._dnd_enabled = enabled
