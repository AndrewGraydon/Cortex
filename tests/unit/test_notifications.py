"""Tests for notification service — priority queue and delivery."""

from __future__ import annotations

from cortex.agent.notifications import Notification, NotificationService
from cortex.hal.display.mock import MockDisplayService


def make_notif(
    priority: int = 2,
    title: str = "Test",
    body: str = "body",
    notif_id: str = "n-001",
) -> Notification:
    return Notification(id=notif_id, priority=priority, title=title, body=body)


class TestImmediateDelivery:
    async def test_deliver_when_not_in_session(self) -> None:
        svc = NotificationService()
        delivered = await svc.notify(make_notif())
        assert delivered
        assert len(svc.history) == 1

    async def test_p4_always_delivered(self) -> None:
        svc = NotificationService()
        svc.in_session = True
        delivered = await svc.notify(make_notif(priority=4, title="URGENT"))
        assert delivered
        assert svc.history[0].priority == 4

    async def test_delivery_sets_timestamp(self) -> None:
        svc = NotificationService()
        await svc.notify(make_notif())
        assert svc.history[0].delivered_at > 0

    async def test_delivery_callback(self) -> None:
        delivered: list[Notification] = []

        async def on_deliver(n: Notification) -> None:
            delivered.append(n)

        svc = NotificationService()
        svc.set_on_deliver(on_deliver)
        await svc.notify(make_notif())
        assert len(delivered) == 1


class TestSessionQueueing:
    async def test_p2_queued_in_session(self) -> None:
        svc = NotificationService()
        svc.in_session = True
        delivered = await svc.notify(make_notif(priority=2))
        assert not delivered
        assert svc.queue_size == 1

    async def test_p0_queued_in_session(self) -> None:
        svc = NotificationService()
        svc.in_session = True
        delivered = await svc.notify(make_notif(priority=0))
        assert not delivered

    async def test_flush_after_session(self) -> None:
        svc = NotificationService()
        svc.in_session = True
        await svc.notify(make_notif(priority=1, notif_id="n1"))
        await svc.notify(make_notif(priority=3, notif_id="n2"))
        await svc.notify(make_notif(priority=0, notif_id="n3"))
        assert svc.queue_size == 3

        svc.in_session = False
        delivered = await svc.flush_queue()
        assert len(delivered) == 3
        # P3 first (highest priority)
        assert delivered[0].priority == 3
        assert delivered[-1].priority == 0
        assert svc.queue_size == 0

    async def test_flush_empty_queue(self) -> None:
        svc = NotificationService()
        delivered = await svc.flush_queue()
        assert delivered == []


class TestDNDMode:
    async def test_dnd_suppresses_low_priority(self) -> None:
        svc = NotificationService(dnd_enabled=True, dnd_start_hour=0, dnd_end_hour=24)
        delivered = await svc.notify(make_notif(priority=2))
        assert not delivered
        assert svc.queue_size == 1

    async def test_dnd_allows_p4(self) -> None:
        svc = NotificationService(dnd_enabled=True, dnd_start_hour=0, dnd_end_hour=24)
        delivered = await svc.notify(make_notif(priority=4))
        assert delivered

    async def test_toggle_dnd(self) -> None:
        svc = NotificationService()
        assert not svc._dnd_enabled
        svc.set_dnd(True)
        assert svc._dnd_enabled
        svc.set_dnd(False)
        assert not svc._dnd_enabled


class TestWithDisplay:
    async def test_p0_shows_text(self) -> None:
        display = MockDisplayService()
        svc = NotificationService(display=display)
        await svc.notify(make_notif(priority=0, title="Badge"))
        assert display._current_text == "Badge"

    async def test_p4_shows_urgent(self) -> None:
        display = MockDisplayService()
        svc = NotificationService(display=display)
        await svc.notify(make_notif(priority=4, title="Fire"))
        assert "URGENT" in display._current_text


class TestQueueManagement:
    async def test_clear_queue(self) -> None:
        svc = NotificationService()
        svc.in_session = True
        await svc.notify(make_notif(notif_id="a"))
        await svc.notify(make_notif(notif_id="b"))
        assert svc.queue_size == 2
        svc.clear_queue()
        assert svc.queue_size == 0

    async def test_history_accumulates(self) -> None:
        svc = NotificationService()
        await svc.notify(make_notif(notif_id="h1"))
        await svc.notify(make_notif(notif_id="h2"))
        assert len(svc.history) == 2
