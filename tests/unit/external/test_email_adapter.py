"""Tests for email adapters (mock, IMAP helpers)."""

from __future__ import annotations

from datetime import UTC, datetime

from cortex.external.email.mock import MockEmailAdapter
from cortex.external.protocols import ExternalServiceAdapter
from cortex.external.types import EmailMessage


def _make_message(
    message_id: str = "msg-1",
    subject: str = "Test Subject",
    sender: str = "test@example.com",
    is_read: bool = False,
) -> EmailMessage:
    return EmailMessage(
        message_id=message_id,
        subject=subject,
        sender=sender,
        date=datetime.now(tz=UTC),
        preview="Test body preview",
        is_read=is_read,
    )


class TestMockEmailProtocol:
    def test_satisfies_external_service_adapter(self) -> None:
        adapter = MockEmailAdapter()
        assert isinstance(adapter, ExternalServiceAdapter)

    def test_service_type(self) -> None:
        assert MockEmailAdapter().service_type == "email"


class TestMockEmailLifecycle:
    async def test_connect(self) -> None:
        adapter = MockEmailAdapter()
        await adapter.connect()
        assert adapter._connected is True

    async def test_disconnect(self) -> None:
        adapter = MockEmailAdapter()
        await adapter.connect()
        await adapter.disconnect()
        assert adapter._connected is False

    async def test_health_check_connected(self) -> None:
        adapter = MockEmailAdapter()
        await adapter.connect()
        assert await adapter.health_check() is True

    async def test_health_check_disconnected(self) -> None:
        adapter = MockEmailAdapter()
        assert await adapter.health_check() is False


class TestMockEmailListMessages:
    async def test_empty_inbox(self) -> None:
        adapter = MockEmailAdapter()
        messages = await adapter.list_messages()
        assert messages == []

    async def test_list_returns_messages(self) -> None:
        adapter = MockEmailAdapter()
        adapter.add_message(_make_message(message_id="m1"))
        messages = await adapter.list_messages()
        assert len(messages) == 1
        assert messages[0].message_id == "m1"

    async def test_list_most_recent_first(self) -> None:
        adapter = MockEmailAdapter()
        adapter.add_message(
            EmailMessage(
                message_id="older",
                subject="Old",
                sender="a@b.com",
                date=datetime(2025, 1, 1, tzinfo=UTC),
            )
        )
        adapter.add_message(
            EmailMessage(
                message_id="newer",
                subject="New",
                sender="a@b.com",
                date=datetime(2025, 6, 1, tzinfo=UTC),
            )
        )
        messages = await adapter.list_messages()
        assert messages[0].message_id == "newer"

    async def test_list_respects_limit(self) -> None:
        adapter = MockEmailAdapter()
        for i in range(10):
            adapter.add_message(_make_message(message_id=f"m{i}"))
        messages = await adapter.list_messages(limit=3)
        assert len(messages) == 3

    async def test_list_unread_only(self) -> None:
        adapter = MockEmailAdapter()
        adapter.add_message(_make_message(message_id="read", is_read=True))
        adapter.add_message(_make_message(message_id="unread", is_read=False))
        messages = await adapter.list_messages(unread_only=True)
        assert len(messages) == 1
        assert messages[0].message_id == "unread"


class TestMockEmailUnreadCount:
    async def test_no_messages(self) -> None:
        adapter = MockEmailAdapter()
        assert await adapter.get_unread_count() == 0

    async def test_mixed_read_unread(self) -> None:
        adapter = MockEmailAdapter()
        adapter.add_message(_make_message(message_id="r", is_read=True))
        adapter.add_message(_make_message(message_id="u1", is_read=False))
        adapter.add_message(_make_message(message_id="u2", is_read=False))
        assert await adapter.get_unread_count() == 2


class TestMockEmailSend:
    async def test_send_message(self) -> None:
        adapter = MockEmailAdapter()
        result = await adapter.send_message(
            to="test@example.com",
            subject="Hello",
            body="World",
        )
        assert result is True
        assert len(adapter._outbox) == 1
        assert adapter._outbox[0]["to"] == "test@example.com"

    async def test_send_multiple(self) -> None:
        adapter = MockEmailAdapter()
        await adapter.send_message("a@b.com", "S1", "B1")
        await adapter.send_message("c@d.com", "S2", "B2")
        assert len(adapter._outbox) == 2


class TestMockEmailSampleMessages:
    def test_add_sample_messages(self) -> None:
        adapter = MockEmailAdapter()
        adapter.add_sample_messages()
        assert len(adapter._inbox) == 3

    async def test_sample_messages_mixed_read(self) -> None:
        adapter = MockEmailAdapter()
        adapter.add_sample_messages()
        unread = await adapter.get_unread_count()
        assert unread == 2  # 2 unread in sample data
