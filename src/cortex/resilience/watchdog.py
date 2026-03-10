"""Systemd and hardware watchdog integration.

SystemdWatchdog: sends sd_notify(WATCHDOG=1) heartbeats to systemd.
No-op on macOS or when not running under systemd.

HardwareWatchdog: stub for BCM2835 /dev/watchdog on Pi (Phase 6 stretch).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os

logger = logging.getLogger(__name__)


def _is_systemd() -> bool:
    """Check if running under systemd with watchdog enabled."""
    return os.environ.get("WATCHDOG_USEC", "") != ""


def _sd_notify(state: str) -> bool:
    """Send sd_notify message. Returns True if sent."""
    # Use systemd.daemon if available, otherwise socket-based fallback
    notify_socket = os.environ.get("NOTIFY_SOCKET")
    if not notify_socket:
        return False

    try:
        import socket

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            if notify_socket.startswith("@"):
                notify_socket = "\0" + notify_socket[1:]
            sock.sendto(state.encode(), notify_socket)
            return True
        finally:
            sock.close()
    except Exception:
        logger.debug("sd_notify failed (not running under systemd?)")
        return False


class SystemdWatchdog:
    """Sends periodic heartbeats to systemd's watchdog timer.

    If running under systemd with WatchdogSec configured, the watchdog
    will restart the service if heartbeats stop. On macOS or without
    systemd, all operations are no-ops.
    """

    def __init__(self, interval_s: float = 10.0) -> None:
        self._interval_s = interval_s
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._enabled = _is_systemd()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def running(self) -> bool:
        return self._running

    def notify(self) -> bool:
        """Send a single watchdog heartbeat. Returns True if sent."""
        if not self._enabled:
            return False
        return _sd_notify("WATCHDOG=1")

    def notify_ready(self) -> bool:
        """Notify systemd that the service is ready."""
        if not self._enabled:
            return False
        return _sd_notify("READY=1")

    def notify_stopping(self) -> bool:
        """Notify systemd that the service is stopping."""
        if not self._enabled:
            return False
        return _sd_notify("STOPPING=1")

    async def start(self) -> None:
        """Start the periodic heartbeat loop."""
        if self._running:
            return
        self._running = True
        if self._enabled:
            self._task = asyncio.create_task(self._heartbeat_loop())
            logger.info(
                "Systemd watchdog started (interval=%.1fs)", self._interval_s,
            )
        else:
            logger.debug("Systemd watchdog disabled (not running under systemd)")

    async def stop(self) -> None:
        """Stop the heartbeat loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._enabled:
            self.notify_stopping()
            logger.info("Systemd watchdog stopped")

    async def _heartbeat_loop(self) -> None:
        """Send heartbeats at the configured interval."""
        while self._running:
            self.notify()
            await asyncio.sleep(self._interval_s)
