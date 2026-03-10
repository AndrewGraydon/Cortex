"""Proactive scheduler — recurring schedules for proactive actions.

Manages daily-at and interval-based recurring triggers. The morning
briefing is the primary use case. Not to be confused with SchedulingService
(user-facing timers) — this is internal to the proactive engine.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any

from cortex.agent.proactive.types import ProactiveSchedule

logger = logging.getLogger(__name__)


class ProactiveScheduler:
    """Manages recurring proactive schedules.

    Supports two modes:
    - Daily at HH:MM (interval_seconds == 0)
    - Every N seconds (interval_seconds > 0)
    """

    def __init__(self) -> None:
        self._schedules: dict[str, ProactiveSchedule] = {}
        self._callbacks: dict[str, Callable[..., Coroutine[Any, Any, None]]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False

    @property
    def schedules(self) -> list[ProactiveSchedule]:
        return list(self._schedules.values())

    def add_daily(
        self,
        schedule_id: str,
        name: str,
        hour: int,
        minute: int,
        callback: Callable[..., Coroutine[Any, Any, None]],
    ) -> ProactiveSchedule:
        """Add a daily schedule that fires at HH:MM."""
        schedule = ProactiveSchedule(
            schedule_id=schedule_id,
            name=name,
            hour=hour,
            minute=minute,
        )
        self._schedules[schedule_id] = schedule
        self._callbacks[schedule_id] = callback
        if self._running:
            self._start_schedule(schedule)
        return schedule

    def add_interval(
        self,
        schedule_id: str,
        name: str,
        interval_seconds: float,
        callback: Callable[..., Coroutine[Any, Any, None]],
    ) -> ProactiveSchedule:
        """Add an interval-based recurring schedule."""
        schedule = ProactiveSchedule(
            schedule_id=schedule_id,
            name=name,
            interval_seconds=interval_seconds,
        )
        self._schedules[schedule_id] = schedule
        self._callbacks[schedule_id] = callback
        if self._running:
            self._start_schedule(schedule)
        return schedule

    def remove(self, schedule_id: str) -> None:
        """Remove a schedule."""
        task = self._tasks.pop(schedule_id, None)
        if task:
            task.cancel()
        self._schedules.pop(schedule_id, None)
        self._callbacks.pop(schedule_id, None)

    async def start(self) -> None:
        """Start all registered schedules."""
        self._running = True
        for schedule in self._schedules.values():
            self._start_schedule(schedule)
        logger.info("ProactiveScheduler started", extra={"count": len(self._schedules)})

    async def stop(self) -> None:
        """Stop all schedules."""
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()
        logger.info("ProactiveScheduler stopped")

    def _start_schedule(self, schedule: ProactiveSchedule) -> None:
        """Start the asyncio task for a schedule."""
        if not schedule.enabled:
            return
        old = self._tasks.pop(schedule.schedule_id, None)
        if old:
            old.cancel()

        if schedule.interval_seconds > 0:
            task = asyncio.create_task(self._interval_loop(schedule))
        else:
            task = asyncio.create_task(self._daily_loop(schedule))
        self._tasks[schedule.schedule_id] = task

    async def _daily_loop(self, schedule: ProactiveSchedule) -> None:
        """Loop that fires once daily at the configured time."""
        try:
            while self._running:
                delay = _seconds_until(schedule.hour, schedule.minute)
                await asyncio.sleep(delay)
                if not self._running:
                    break
                await self._fire(schedule)
                # Sleep at least 60s to avoid double-firing
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass

    async def _interval_loop(self, schedule: ProactiveSchedule) -> None:
        """Loop that fires every N seconds."""
        try:
            while self._running:
                await asyncio.sleep(schedule.interval_seconds)
                if not self._running:
                    break
                await self._fire(schedule)
        except asyncio.CancelledError:
            pass

    async def _fire(self, schedule: ProactiveSchedule) -> None:
        """Fire a schedule's callback."""
        schedule.last_fired = time.time()
        callback = self._callbacks.get(schedule.schedule_id)
        if callback is None:
            return
        try:
            await callback()
            logger.info("Schedule '%s' fired", schedule.name)
        except Exception:
            logger.exception("Schedule '%s' callback failed", schedule.name)


def _seconds_until(hour: int, minute: int) -> float:
    """Calculate seconds until next occurrence of HH:MM."""
    now = datetime.now()  # noqa: DTZ005
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        # Already past today — schedule for tomorrow
        target = target.replace(day=target.day + 1)
    return (target - now).total_seconds()
