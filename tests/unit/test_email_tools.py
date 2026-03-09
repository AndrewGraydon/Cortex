"""Tests for email tools (query and send)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from cortex.agent.protocols import Tool
from cortex.agent.tools.builtin.email_tool import (
    EmailQueryTool,
    EmailSendTool,
    set_email_backend,
)
from cortex.external.email.mock import MockEmailAdapter
from cortex.external.types import EmailMessage


@pytest.fixture(autouse=True)
def _reset_backend() -> Any:
    """Reset email backend before/after each test."""
    set_email_backend(imap=None, smtp=None)
    yield
    set_email_backend(imap=None, smtp=None)


def _make_message(
    message_id: str = "t1",
    subject: str = "Test",
    is_read: bool = False,
) -> EmailMessage:
    return EmailMessage(
        message_id=message_id,
        subject=subject,
        sender="sender@example.com",
        date=datetime.now(tz=UTC),
        preview="Preview text",
        is_read=is_read,
    )


# --- Protocol compliance ---


class TestEmailToolProtocol:
    def test_query_satisfies_tool(self) -> None:
        assert isinstance(EmailQueryTool(), Tool)

    def test_send_satisfies_tool(self) -> None:
        assert isinstance(EmailSendTool(), Tool)


# --- EmailQueryTool properties ---


class TestEmailQueryToolProperties:
    def test_name(self) -> None:
        assert EmailQueryTool().name == "email_query"

    def test_permission_tier(self) -> None:
        assert EmailQueryTool().permission_tier == 0

    def test_schema(self) -> None:
        schema = EmailQueryTool().get_schema()
        assert schema["name"] == "email_query"
        assert "unread_only" in schema["parameters"]["properties"]


# --- EmailQueryTool execution ---


class TestEmailQueryToolExecute:
    async def test_no_backend(self) -> None:
        result = await EmailQueryTool().execute({})
        assert result.success is True
        assert result.data == []
        assert "not configured" in result.display_text.lower()

    async def test_empty_inbox(self) -> None:
        adapter = MockEmailAdapter()
        set_email_backend(imap=adapter)
        result = await EmailQueryTool().execute({})
        assert result.success is True
        assert result.data == []
        assert "no" in result.display_text.lower()

    async def test_returns_messages(self) -> None:
        adapter = MockEmailAdapter()
        adapter.add_message(_make_message(message_id="m1", subject="Hello"))
        set_email_backend(imap=adapter)

        result = await EmailQueryTool().execute({})
        assert result.success is True
        assert len(result.data) == 1
        assert result.data[0]["subject"] == "Hello"
        assert "1 email" in result.display_text

    async def test_multiple_messages_display(self) -> None:
        adapter = MockEmailAdapter()
        for i in range(3):
            adapter.add_message(_make_message(message_id=f"m{i}", subject=f"Email {i}"))
        set_email_backend(imap=adapter)

        result = await EmailQueryTool().execute({})
        assert len(result.data) == 3
        assert "3 emails" in result.display_text

    async def test_unread_only(self) -> None:
        adapter = MockEmailAdapter()
        adapter.add_message(_make_message(message_id="read", is_read=True))
        adapter.add_message(_make_message(message_id="unread", is_read=False))
        set_email_backend(imap=adapter)

        result = await EmailQueryTool().execute({"unread_only": True})
        assert len(result.data) == 1
        assert result.data[0]["message_id"] == "unread"

    async def test_limit_parameter(self) -> None:
        adapter = MockEmailAdapter()
        for i in range(10):
            adapter.add_message(_make_message(message_id=f"m{i}"))
        set_email_backend(imap=adapter)

        result = await EmailQueryTool().execute({"limit": 2})
        assert len(result.data) == 2

    async def test_limit_capped_at_20(self) -> None:
        adapter = MockEmailAdapter()
        set_email_backend(imap=adapter)
        result = await EmailQueryTool().execute({"limit": 100})
        assert result.success is True  # No crash, just works

    async def test_message_data_format(self) -> None:
        adapter = MockEmailAdapter()
        adapter.add_message(_make_message())
        set_email_backend(imap=adapter)

        result = await EmailQueryTool().execute({})
        msg = result.data[0]
        assert "message_id" in msg
        assert "subject" in msg
        assert "sender" in msg
        assert "date" in msg
        assert "preview" in msg
        assert "is_read" in msg


# --- EmailSendTool properties ---


class TestEmailSendToolProperties:
    def test_name(self) -> None:
        assert EmailSendTool().name == "email_send"

    def test_permission_tier(self) -> None:
        assert EmailSendTool().permission_tier == 2

    def test_schema_required_fields(self) -> None:
        schema = EmailSendTool().get_schema()
        assert schema["parameters"]["required"] == ["to", "subject", "body"]


# --- EmailSendTool execution ---


class TestEmailSendToolExecute:
    async def test_no_backend(self) -> None:
        result = await EmailSendTool().execute(
            {
                "to": "a@b.com",
                "subject": "Hi",
                "body": "Hello",
            }
        )
        assert result.success is False
        assert "not configured" in result.error.lower()

    async def test_missing_to(self) -> None:
        adapter = MockEmailAdapter()
        set_email_backend(imap=adapter)
        result = await EmailSendTool().execute({"subject": "Hi", "body": "Hello"})
        assert result.success is False
        assert "recipient" in result.error.lower()

    async def test_missing_subject(self) -> None:
        adapter = MockEmailAdapter()
        set_email_backend(imap=adapter)
        result = await EmailSendTool().execute({"to": "a@b.com", "body": "Hello"})
        assert result.success is False
        assert "subject" in result.error.lower()

    async def test_missing_body(self) -> None:
        adapter = MockEmailAdapter()
        set_email_backend(imap=adapter)
        result = await EmailSendTool().execute({"to": "a@b.com", "subject": "Hi"})
        assert result.success is False
        assert "body" in result.error.lower()

    async def test_send_success(self) -> None:
        adapter = MockEmailAdapter()
        set_email_backend(imap=adapter)
        result = await EmailSendTool().execute(
            {
                "to": "test@example.com",
                "subject": "Test Subject",
                "body": "Test body",
            }
        )
        assert result.success is True
        assert result.data["to"] == "test@example.com"
        assert "sent" in result.display_text.lower()

    async def test_send_stores_in_outbox(self) -> None:
        adapter = MockEmailAdapter()
        set_email_backend(imap=adapter)
        await EmailSendTool().execute(
            {
                "to": "a@b.com",
                "subject": "S",
                "body": "B",
            }
        )
        assert len(adapter._outbox) == 1
