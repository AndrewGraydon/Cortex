"""Tests for notification send tool (external push notifications)."""

from __future__ import annotations

from typing import Any

import pytest

from cortex.agent.protocols import Tool
from cortex.agent.tools.builtin.notification_send import (
    NotificationSendExternalTool,
    set_notification_backend,
)
from cortex.external.messaging.mock import MockMessagingAdapter


@pytest.fixture(autouse=True)
def _reset_backend() -> Any:
    """Reset notification backend before/after each test."""
    set_notification_backend(None)
    yield
    set_notification_backend(None)


class TestNotificationToolProtocol:
    def test_satisfies_tool(self) -> None:
        assert isinstance(NotificationSendExternalTool(), Tool)


class TestNotificationToolProperties:
    def test_name(self) -> None:
        assert NotificationSendExternalTool().name == "notification_send_external"

    def test_permission_tier(self) -> None:
        assert NotificationSendExternalTool().permission_tier == 1

    def test_schema(self) -> None:
        schema = NotificationSendExternalTool().get_schema()
        assert schema["name"] == "notification_send_external"
        assert "message" in schema["parameters"]["properties"]
        assert schema["parameters"]["required"] == ["message"]


class TestNotificationToolExecute:
    async def test_no_backend(self) -> None:
        result = await NotificationSendExternalTool().execute({"message": "Hello"})
        assert result.success is False
        assert "not configured" in result.error.lower()

    async def test_missing_message(self) -> None:
        adapter = MockMessagingAdapter()
        set_notification_backend(adapter)
        result = await NotificationSendExternalTool().execute({})
        assert result.success is False
        assert "message" in result.error.lower()

    async def test_empty_message(self) -> None:
        adapter = MockMessagingAdapter()
        set_notification_backend(adapter)
        result = await NotificationSendExternalTool().execute({"message": "  "})
        assert result.success is False

    async def test_send_success(self) -> None:
        adapter = MockMessagingAdapter()
        set_notification_backend(adapter)
        result = await NotificationSendExternalTool().execute({"message": "Test notification"})
        assert result.success is True
        assert "sent" in result.display_text.lower()
        assert adapter.sent_count == 1

    async def test_send_with_title(self) -> None:
        adapter = MockMessagingAdapter()
        set_notification_backend(adapter)
        result = await NotificationSendExternalTool().execute(
            {
                "message": "Body text",
                "title": "Alert Title",
            }
        )
        assert result.success is True
        assert adapter.sent_messages[0]["title"] == "Alert Title"

    async def test_send_with_priority(self) -> None:
        adapter = MockMessagingAdapter()
        set_notification_backend(adapter)
        result = await NotificationSendExternalTool().execute(
            {
                "message": "Urgent!",
                "priority": 5,
            }
        )
        assert result.success is True
        assert adapter.sent_messages[0]["priority"] == 5

    async def test_invalid_priority_defaults_to_3(self) -> None:
        adapter = MockMessagingAdapter()
        set_notification_backend(adapter)
        result = await NotificationSendExternalTool().execute(
            {
                "message": "Test",
                "priority": 99,
            }
        )
        assert result.success is True
        assert adapter.sent_messages[0]["priority"] == 3

    async def test_display_text_truncated(self) -> None:
        adapter = MockMessagingAdapter()
        set_notification_backend(adapter)
        long_msg = "A" * 200
        result = await NotificationSendExternalTool().execute({"message": long_msg})
        assert result.success is True
        assert len(result.display_text) < 200  # truncated in display
