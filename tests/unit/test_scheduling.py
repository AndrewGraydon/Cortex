"""Tests for scheduling service — SQLite-persisted timers."""

from __future__ import annotations

import asyncio

import pytest

from cortex.agent.scheduling import ScheduledTimer, SchedulingService


@pytest.fixture
async def scheduler(tmp_path) -> SchedulingService:
    db_path = str(tmp_path / "test_schedules.db")
    svc = SchedulingService(db_path=db_path)
    await svc.start()
    yield svc
    await svc.stop()


class TestTimerCreation:
    async def test_create_timer(self, scheduler: SchedulingService) -> None:
        timer = await scheduler.create_timer(60, "tea")
        assert timer.label == "tea"
        assert timer.duration_seconds == 60
        assert timer.status == "active"
        assert timer.fires_at > timer.created_at

    async def test_create_timer_default_label(self, scheduler: SchedulingService) -> None:
        timer = await scheduler.create_timer(30)
        assert "30s" in timer.label

    async def test_create_timer_persisted(self, scheduler: SchedulingService) -> None:
        await scheduler.create_timer(60, "test")
        count = await scheduler.timer_count()
        assert count == 1

    async def test_max_timers_enforced(self, tmp_path) -> None:
        svc = SchedulingService(db_path=str(tmp_path / "max.db"), max_timers=2)
        await svc.start()
        await svc.create_timer(300, "t1")
        await svc.create_timer(300, "t2")
        with pytest.raises(ValueError, match="Maximum"):
            await svc.create_timer(300, "t3")
        await svc.stop()


class TestTimerQuery:
    async def test_get_active_timers(self, scheduler: SchedulingService) -> None:
        await scheduler.create_timer(300, "t1")
        await scheduler.create_timer(600, "t2")
        active = await scheduler.get_active_timers()
        assert len(active) == 2

    async def test_get_all_timers(self, scheduler: SchedulingService) -> None:
        t = await scheduler.create_timer(300, "to_cancel")
        await scheduler.cancel_timer(t.id)
        await scheduler.create_timer(300, "active")
        all_timers = await scheduler.get_all_timers()
        assert len(all_timers) == 2
        active = await scheduler.get_active_timers()
        assert len(active) == 1


class TestTimerCancellation:
    async def test_cancel_by_id(self, scheduler: SchedulingService) -> None:
        timer = await scheduler.create_timer(300, "to_cancel")
        result = await scheduler.cancel_timer(timer.id)
        assert result is not None
        assert result.status == "cancelled"
        count = await scheduler.timer_count()
        assert count == 0

    async def test_cancel_nonexistent(self, scheduler: SchedulingService) -> None:
        result = await scheduler.cancel_timer("nonexistent")
        assert result is None

    async def test_cancel_by_label(self, scheduler: SchedulingService) -> None:
        await scheduler.create_timer(300, "tea timer")
        result = await scheduler.cancel_by_label("tea")
        assert result is not None
        assert result.status == "cancelled"

    async def test_cancel_by_label_no_match(self, scheduler: SchedulingService) -> None:
        await scheduler.create_timer(300, "tea timer")
        result = await scheduler.cancel_by_label("coffee")
        assert result is None


class TestTimerFiring:
    async def test_timer_fires(self, tmp_path) -> None:
        fired_timers: list[ScheduledTimer] = []

        async def on_fire(timer: ScheduledTimer) -> None:
            fired_timers.append(timer)

        svc = SchedulingService(db_path=str(tmp_path / "fire.db"), on_fire=on_fire)
        await svc.start()
        await svc.create_timer(1, "quick")  # 1 second
        await asyncio.sleep(1.5)
        assert len(fired_timers) == 1
        assert fired_timers[0].label == "quick"
        # Should be marked as fired in DB
        active = await svc.get_active_timers()
        assert len(active) == 0
        await svc.stop()

    async def test_cancelled_timer_does_not_fire(self, tmp_path) -> None:
        fired_timers: list[ScheduledTimer] = []

        async def on_fire(timer: ScheduledTimer) -> None:
            fired_timers.append(timer)

        svc = SchedulingService(db_path=str(tmp_path / "nofire.db"), on_fire=on_fire)
        await svc.start()
        timer = await svc.create_timer(1, "cancel_me")
        await svc.cancel_timer(timer.id)
        await asyncio.sleep(1.5)
        assert len(fired_timers) == 0
        await svc.stop()


class TestRebootRecovery:
    async def test_recover_pending_timer(self, tmp_path) -> None:
        db_path = str(tmp_path / "recover.db")
        fired_timers: list[ScheduledTimer] = []

        async def on_fire(timer: ScheduledTimer) -> None:
            fired_timers.append(timer)

        # Create a timer that fires in 5 seconds
        svc1 = SchedulingService(db_path=db_path, on_fire=on_fire)
        await svc1.start()
        await svc1.create_timer(5, "survive_reboot")
        await svc1.stop()

        # "Reboot" — create new service with same DB
        svc2 = SchedulingService(db_path=db_path, on_fire=on_fire)
        await svc2.start()

        # Timer should still be active
        active = await svc2.get_active_timers()
        assert len(active) == 1
        assert active[0].label == "survive_reboot"
        await svc2.stop()

    async def test_recover_past_due_timer(self, tmp_path) -> None:
        db_path = str(tmp_path / "pastdue.db")
        fired_timers: list[ScheduledTimer] = []

        async def on_fire(timer: ScheduledTimer) -> None:
            fired_timers.append(timer)

        # Create a timer that fires in 1 second
        svc1 = SchedulingService(db_path=db_path, on_fire=on_fire)
        await svc1.start()
        await svc1.create_timer(1, "past_due")
        await svc1.stop()

        # Wait for it to be past due
        await asyncio.sleep(1.5)

        # Restart — should fire immediately
        svc2 = SchedulingService(db_path=db_path, on_fire=on_fire)
        await svc2.start()
        # Give it a moment to recover
        await asyncio.sleep(0.1)
        assert len(fired_timers) == 1
        assert fired_timers[0].label == "past_due"
        await svc2.stop()


class TestLifecycle:
    async def test_operations_before_start_raise(self, tmp_path) -> None:
        svc = SchedulingService(db_path=str(tmp_path / "nope.db"))
        with pytest.raises(RuntimeError, match="not started"):
            await svc.get_active_timers()

    async def test_stop_cancels_tasks(self, tmp_path) -> None:
        svc = SchedulingService(db_path=str(tmp_path / "stop.db"))
        await svc.start()
        await svc.create_timer(300, "long_timer")
        assert len(svc._tasks) == 1
        await svc.stop()
        assert len(svc._tasks) == 0
