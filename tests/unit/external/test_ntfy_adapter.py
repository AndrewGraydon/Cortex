"""Tests for ntfy messaging adapter (mock)."""

from __future__ import annotations

from cortex.external.messaging.mock import MockMessagingAdapter
from cortex.external.protocols import ExternalServiceAdapter
from cortex.external.types import ExternalNotification


class TestMockMessagingProtocol:
    def test_satisfies_external_service_adapter(self) -> None:
        adapter = MockMessagingAdapter()
        assert isinstance(adapter, ExternalServiceAdapter)

    def test_service_type(self) -> None:
        assert MockMessagingAdapter().service_type == "messaging"


class TestMockMessagingLifecycle:
    async def test_connect(self) -> None:
        adapter = MockMessagingAdapter()
        await adapter.connect()
        assert adapter._connected is True

    async def test_disconnect(self) -> None:
        adapter = MockMessagingAdapter()
        await adapter.connect()
        await adapter.disconnect()
        assert adapter._connected is False

    async def test_health_check_connected(self) -> None:
        adapter = MockMessagingAdapter()
        await adapter.connect()
        assert await adapter.health_check() is True

    async def test_health_check_disconnected(self) -> None:
        adapter = MockMessagingAdapter()
        assert await adapter.health_check() is False


class TestMockMessagingSend:
    async def test_send_notification(self) -> None:
        adapter = MockMessagingAdapter()
        notification = ExternalNotification(message="Hello world")
        result = await adapter.send_notification(notification)
        assert result is True
        assert adapter.sent_count == 1

    async def test_send_with_title_and_priority(self) -> None:
        adapter = MockMessagingAdapter()
        notification = ExternalNotification(
            message="Alert!",
            title="Important",
            priority=5,
            tags=["warning"],
        )
        result = await adapter.send_notification(notification)
        assert result is True
        sent = adapter.sent_messages[0]
        assert sent["title"] == "Important"
        assert sent["priority"] == 5
        assert sent["tags"] == ["warning"]

    async def test_send_uses_default_topic(self) -> None:
        adapter = MockMessagingAdapter(default_topic="test-topic")
        notification = ExternalNotification(message="Test")
        await adapter.send_notification(notification)
        assert adapter.sent_messages[0]["topic"] == "test-topic"

    async def test_send_with_custom_topic(self) -> None:
        adapter = MockMessagingAdapter(default_topic="default")
        notification = ExternalNotification(message="Test", topic="custom")
        await adapter.send_notification(notification)
        assert adapter.sent_messages[0]["topic"] == "custom"

    async def test_send_multiple(self) -> None:
        adapter = MockMessagingAdapter()
        for i in range(5):
            await adapter.send_notification(ExternalNotification(message=f"Message {i}"))
        assert adapter.sent_count == 5

    async def test_sent_messages_list(self) -> None:
        adapter = MockMessagingAdapter()
        await adapter.send_notification(ExternalNotification(message="First"))
        await adapter.send_notification(ExternalNotification(message="Second"))
        msgs = adapter.sent_messages
        assert len(msgs) == 2
        assert msgs[0]["message"] == "First"
        assert msgs[1]["message"] == "Second"
