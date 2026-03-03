"""Scheduling service — SQLite-persisted timers with asyncio scheduling.

Survives reboots by persisting timer state to SQLite and recovering
on startup. Fires notifications through the notification service.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

CREATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS timers (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    created_at REAL NOT NULL,
    fires_at REAL NOT NULL,
    status TEXT DEFAULT 'active',
    notification_priority INTEGER DEFAULT 2
);
CREATE INDEX IF NOT EXISTS idx_timers_status ON timers(status);
CREATE INDEX IF NOT EXISTS idx_timers_fires ON timers(fires_at);
"""


@dataclass
class ScheduledTimer:
    """A persisted timer."""

    id: str
    label: str
    duration_seconds: int
    created_at: float
    fires_at: float
    status: str = "active"
    notification_priority: int = 2


class SchedulingService:
    """Manages timers with SQLite persistence and asyncio scheduling.

    Args:
        db_path: Path to the SQLite database.
        on_fire: Async callback invoked when a timer fires.
        max_timers: Maximum active timers allowed.
    """

    def __init__(
        self,
        db_path: str = "data/schedules.db",
        on_fire: Any = None,
        max_timers: int = 20,
    ) -> None:
        self._db_path = db_path
        self._on_fire = on_fire
        self._max_timers = max_timers
        self._db: aiosqlite.Connection | None = None
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False

    async def start(self) -> None:
        """Open database, create tables, recover pending timers."""
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(CREATE_SCHEMA)
        await self._db.commit()
        self._running = True
        await self._recover_timers()

    async def stop(self) -> None:
        """Cancel all pending tasks and close the database."""
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()
        if self._db is not None:
            await self._db.close()
            self._db = None

    def _ensure_started(self) -> aiosqlite.Connection:
        if self._db is None:
            msg = "SchedulingService not started"
            raise RuntimeError(msg)
        return self._db

    async def create_timer(
        self,
        duration_seconds: int,
        label: str = "",
        notification_priority: int = 2,
    ) -> ScheduledTimer:
        """Create and persist a new timer."""
        db = self._ensure_started()

        # Check active count
        active = await self.get_active_timers()
        if len(active) >= self._max_timers:
            msg = f"Maximum {self._max_timers} active timers reached"
            raise ValueError(msg)

        now = time.time()
        timer = ScheduledTimer(
            id=uuid.uuid4().hex[:8],
            label=label or f"{duration_seconds}s timer",
            duration_seconds=duration_seconds,
            created_at=now,
            fires_at=now + duration_seconds,
            notification_priority=notification_priority,
        )

        await db.execute(
            """INSERT INTO timers
               (id, label, duration_seconds, created_at, fires_at, status, notification_priority)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                timer.id,
                timer.label,
                timer.duration_seconds,
                timer.created_at,
                timer.fires_at,
                timer.status,
                timer.notification_priority,
            ),
        )
        await db.commit()

        self._schedule_task(timer)
        logger.info("Timer '%s' created, fires at %.1f", timer.label, timer.fires_at)
        return timer

    async def get_active_timers(self) -> list[ScheduledTimer]:
        """Get all active (non-fired, non-cancelled) timers."""
        db = self._ensure_started()
        cursor = await db.execute(
            "SELECT id, label, duration_seconds, created_at, fires_at, "
            "status, notification_priority FROM timers WHERE status = 'active'"
        )
        rows = await cursor.fetchall()
        return [self._row_to_timer(tuple(row)) for row in rows]

    async def cancel_timer(self, timer_id: str) -> ScheduledTimer | None:
        """Cancel an active timer by ID."""
        db = self._ensure_started()
        cursor = await db.execute(
            "SELECT id, label, duration_seconds, created_at, fires_at, "
            "status, notification_priority FROM timers WHERE id = ? AND status = 'active'",
            (timer_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        timer = self._row_to_timer(tuple(row))
        await db.execute(
            "UPDATE timers SET status = 'cancelled' WHERE id = ?",
            (timer_id,),
        )
        await db.commit()

        # Cancel the asyncio task
        task = self._tasks.pop(timer_id, None)
        if task:
            task.cancel()

        timer.status = "cancelled"
        logger.info("Timer '%s' cancelled", timer.label)
        return timer

    async def cancel_by_label(self, label: str) -> ScheduledTimer | None:
        """Cancel the first active timer matching the label."""
        timers = await self.get_active_timers()
        for timer in timers:
            if label.lower() in timer.label.lower():
                return await self.cancel_timer(timer.id)
        return None

    async def timer_count(self) -> int:
        """Count active timers."""
        db = self._ensure_started()
        cursor = await db.execute("SELECT COUNT(*) FROM timers WHERE status = 'active'")
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def get_all_timers(self) -> list[ScheduledTimer]:
        """Get all timers (any status)."""
        db = self._ensure_started()
        cursor = await db.execute(
            "SELECT id, label, duration_seconds, created_at, fires_at, "
            "status, notification_priority FROM timers ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [self._row_to_timer(tuple(row)) for row in rows]

    # --- Internal ---

    def _schedule_task(self, timer: ScheduledTimer) -> None:
        """Schedule an asyncio task to fire the timer."""
        delay = max(0.0, timer.fires_at - time.time())
        task = asyncio.create_task(self._wait_and_fire(timer, delay))
        self._tasks[timer.id] = task

    async def _wait_and_fire(self, timer: ScheduledTimer, delay: float) -> None:
        """Wait for the delay then fire the timer."""
        try:
            await asyncio.sleep(delay)
            if not self._running:
                return
            await self._fire_timer(timer)
        except asyncio.CancelledError:
            pass

    async def _fire_timer(self, timer: ScheduledTimer) -> None:
        """Mark timer as fired and invoke callback."""
        db = self._ensure_started()
        await db.execute(
            "UPDATE timers SET status = 'fired' WHERE id = ? AND status = 'active'",
            (timer.id,),
        )
        await db.commit()
        self._tasks.pop(timer.id, None)
        logger.info("Timer '%s' fired", timer.label)

        if self._on_fire:
            try:
                await self._on_fire(timer)
            except Exception:
                logger.exception("Timer fire callback failed for '%s'", timer.label)

    async def _recover_timers(self) -> None:
        """On startup, reschedule active timers and fire any that are past due."""
        timers = await self.get_active_timers()
        now = time.time()
        for timer in timers:
            if timer.fires_at <= now:
                # Past due — fire immediately
                logger.info("Recovering past-due timer '%s'", timer.label)
                await self._fire_timer(timer)
            else:
                # Still pending — reschedule
                logger.info(
                    "Recovering timer '%s' (%.1fs remaining)",
                    timer.label,
                    timer.fires_at - now,
                )
                self._schedule_task(timer)

    @staticmethod
    def _row_to_timer(row: tuple[object, ...]) -> ScheduledTimer:
        return ScheduledTimer(
            id=str(row[0]),
            label=str(row[1]),
            duration_seconds=int(str(row[2])),
            created_at=float(str(row[3])),
            fires_at=float(str(row[4])),
            status=str(row[5]),
            notification_priority=int(str(row[6])),
        )
