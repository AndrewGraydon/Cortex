"""Tests for ProactiveScheduler — recurring schedule management."""

from __future__ import annotations

import asyncio

import pytest

from cortex.agent.proactive.scheduler import ProactiveScheduler, _seconds_until


class TestSecondsUntil:
    def test_future_today(self) -> None:
        # _seconds_until always returns a positive number
        result = _seconds_until(23, 59)
        assert result > 0

    def test_returns_positive(self) -> None:
        result = _seconds_until(0, 0)
        assert result > 0


class TestProactiveScheduler:
    @pytest.fixture()
    def scheduler(self) -> ProactiveScheduler:
        return ProactiveScheduler()

    def test_empty_schedules(self, scheduler: ProactiveScheduler) -> None:
        assert len(scheduler.schedules) == 0

    def test_add_daily(self, scheduler: ProactiveScheduler) -> None:
        async def noop() -> None:
            pass

        scheduler.add_daily("test", "Test Daily", 7, 0, noop)
        assert len(scheduler.schedules) == 1
        s = scheduler.schedules[0]
        assert s.schedule_id == "test"
        assert s.name == "Test Daily"
        assert s.hour == 7
        assert s.minute == 0
        assert s.interval_seconds == 0.0

    def test_add_interval(self, scheduler: ProactiveScheduler) -> None:
        async def noop() -> None:
            pass

        scheduler.add_interval("test", "Test Interval", 60.0, noop)
        assert len(scheduler.schedules) == 1
        s = scheduler.schedules[0]
        assert s.interval_seconds == 60.0

    def test_remove(self, scheduler: ProactiveScheduler) -> None:
        async def noop() -> None:
            pass

        scheduler.add_daily("test", "Test", 7, 0, noop)
        assert len(scheduler.schedules) == 1
        scheduler.remove("test")
        assert len(scheduler.schedules) == 0

    def test_remove_nonexistent(self, scheduler: ProactiveScheduler) -> None:
        scheduler.remove("nonexistent")  # should not raise

    @pytest.mark.asyncio()
    async def test_start_stop(self, scheduler: ProactiveScheduler) -> None:
        async def noop() -> None:
            pass

        scheduler.add_interval("test", "Test", 3600.0, noop)
        await scheduler.start()
        assert scheduler._running is True
        await scheduler.stop()
        assert scheduler._running is False

    @pytest.mark.asyncio()
    async def test_interval_fires(self) -> None:
        scheduler = ProactiveScheduler()
        fired: list[bool] = []

        async def callback() -> None:
            fired.append(True)

        scheduler.add_interval("test", "Test", 0.05, callback)
        await scheduler.start()
        await asyncio.sleep(0.15)
        await scheduler.stop()

        assert len(fired) >= 1

    @pytest.mark.asyncio()
    async def test_schedule_enabled_flag(self) -> None:
        scheduler = ProactiveScheduler()
        fired: list[bool] = []

        async def callback() -> None:
            fired.append(True)

        s = scheduler.add_interval("test", "Test", 0.05, callback)
        s.enabled = False
        await scheduler.start()
        await asyncio.sleep(0.15)
        await scheduler.stop()

        assert len(fired) == 0

    @pytest.mark.asyncio()
    async def test_add_during_running(self) -> None:
        scheduler = ProactiveScheduler()
        fired: list[bool] = []

        async def callback() -> None:
            fired.append(True)

        await scheduler.start()
        scheduler.add_interval("test", "Test", 0.05, callback)
        await asyncio.sleep(0.15)
        await scheduler.stop()

        assert len(fired) >= 1
