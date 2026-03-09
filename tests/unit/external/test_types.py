"""Tests for external service data types."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cortex.external.types import (
    CalendarEvent,
    EmailMessage,
    ExternalNotification,
    ServiceStatus,
)


class TestServiceStatus:
    def test_status_values(self) -> None:
        assert ServiceStatus.CONNECTED.value == "connected"
        assert ServiceStatus.DISCONNECTED.value == "disconnected"
        assert ServiceStatus.ERROR.value == "error"
        assert ServiceStatus.DISABLED.value == "disabled"

    def test_all_statuses_exist(self) -> None:
        assert len(ServiceStatus) == 4


class TestCalendarEvent:
    def test_basic_construction(self) -> None:
        now = datetime(2026, 3, 5, 14, 0, tzinfo=UTC)
        end = datetime(2026, 3, 5, 15, 0, tzinfo=UTC)
        event = CalendarEvent(
            uid="ev-001",
            summary="Team standup",
            start=now,
            end=end,
        )
        assert event.uid == "ev-001"
        assert event.summary == "Team standup"
        assert event.description == ""
        assert event.location == ""
        assert event.all_day is False

    def test_all_day_event(self) -> None:
        now = datetime(2026, 3, 5, tzinfo=UTC)
        end = datetime(2026, 3, 6, tzinfo=UTC)
        event = CalendarEvent(
            uid="ev-002",
            summary="Company holiday",
            start=now,
            end=end,
            all_day=True,
        )
        assert event.all_day is True

    def test_frozen(self) -> None:
        now = datetime(2026, 3, 5, 14, 0, tzinfo=UTC)
        end = datetime(2026, 3, 5, 15, 0, tzinfo=UTC)
        event = CalendarEvent(uid="ev-001", summary="Test", start=now, end=end)
        with pytest.raises(AttributeError):
            event.summary = "Changed"  # type: ignore[misc]

    def test_format_display_timed_event(self) -> None:
        start = datetime(2026, 3, 5, 14, 30, tzinfo=UTC)
        end = datetime(2026, 3, 5, 15, 30, tzinfo=UTC)
        event = CalendarEvent(uid="ev-001", summary="Meeting", start=start, end=end)
        display = event.format_display()
        assert "Meeting" in display
        assert "2:30 PM" in display
        assert "3:30 PM" in display

    def test_format_display_all_day(self) -> None:
        start = datetime(2026, 3, 5, tzinfo=UTC)
        end = datetime(2026, 3, 6, tzinfo=UTC)
        event = CalendarEvent(uid="ev-002", summary="Holiday", start=start, end=end, all_day=True)
        display = event.format_display()
        assert "Holiday" in display
        assert "all day" in display

    def test_with_location_and_description(self) -> None:
        now = datetime(2026, 3, 5, 14, 0, tzinfo=UTC)
        end = datetime(2026, 3, 5, 15, 0, tzinfo=UTC)
        event = CalendarEvent(
            uid="ev-003",
            summary="Client call",
            start=now,
            end=end,
            description="Quarterly review",
            location="Room 42",
        )
        assert event.description == "Quarterly review"
        assert event.location == "Room 42"


class TestEmailMessage:
    def test_basic_construction(self) -> None:
        now = datetime(2026, 3, 5, 10, 0, tzinfo=UTC)
        msg = EmailMessage(
            message_id="msg-001",
            subject="Quarterly report",
            sender="alice@example.com",
            date=now,
        )
        assert msg.message_id == "msg-001"
        assert msg.subject == "Quarterly report"
        assert msg.sender == "alice@example.com"
        assert msg.preview == ""
        assert msg.is_read is False

    def test_read_message(self) -> None:
        now = datetime(2026, 3, 5, 10, 0, tzinfo=UTC)
        msg = EmailMessage(
            message_id="msg-002",
            subject="Re: Project update",
            sender="bob@example.com",
            date=now,
            is_read=True,
        )
        assert msg.is_read is True

    def test_frozen(self) -> None:
        now = datetime(2026, 3, 5, 10, 0, tzinfo=UTC)
        msg = EmailMessage(message_id="msg-001", subject="Test", sender="a@b.com", date=now)
        with pytest.raises(AttributeError):
            msg.subject = "Changed"  # type: ignore[misc]

    def test_format_display_unread(self) -> None:
        now = datetime(2026, 3, 5, 10, 0, tzinfo=UTC)
        msg = EmailMessage(
            message_id="msg-001",
            subject="Invoice",
            sender="billing@corp.com",
            date=now,
        )
        display = msg.format_display()
        assert "billing@corp.com" in display
        assert "Invoice" in display
        assert "(unread)" in display

    def test_format_display_read(self) -> None:
        now = datetime(2026, 3, 5, 10, 0, tzinfo=UTC)
        msg = EmailMessage(
            message_id="msg-002",
            subject="Done",
            sender="alice@example.com",
            date=now,
            is_read=True,
        )
        display = msg.format_display()
        assert "(unread)" not in display

    def test_with_preview(self) -> None:
        now = datetime(2026, 3, 5, 10, 0, tzinfo=UTC)
        msg = EmailMessage(
            message_id="msg-003",
            subject="Meeting notes",
            sender="carol@example.com",
            date=now,
            preview="Here are the key takeaways from today's meeting...",
        )
        assert msg.preview.startswith("Here are")


class TestExternalNotification:
    def test_basic_construction(self) -> None:
        notif = ExternalNotification(message="Timer complete")
        assert notif.message == "Timer complete"
        assert notif.title == ""
        assert notif.priority == 3
        assert notif.tags == []
        assert notif.topic == ""

    def test_with_all_fields(self) -> None:
        notif = ExternalNotification(
            message="Server disk 90% full",
            title="Disk Warning",
            priority=4,
            tags=["warning", "disk"],
            topic="alerts",
        )
        assert notif.title == "Disk Warning"
        assert notif.priority == 4
        assert notif.tags == ["warning", "disk"]
        assert notif.topic == "alerts"

    def test_frozen(self) -> None:
        notif = ExternalNotification(message="Test")
        with pytest.raises(AttributeError):
            notif.message = "Changed"  # type: ignore[misc]

    def test_default_tags_independent(self) -> None:
        """Ensure default list factory creates independent instances."""
        n1 = ExternalNotification(message="A")
        n2 = ExternalNotification(message="B")
        assert n1.tags is not n2.tags
