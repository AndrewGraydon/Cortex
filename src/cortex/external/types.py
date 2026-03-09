"""External service data types — calendar events, emails, notifications."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime


class ServiceStatus(enum.Enum):
    """Health status of an external service."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass(frozen=True)
class CalendarEvent:
    """A calendar event from any calendar provider."""

    uid: str
    summary: str
    start: datetime
    end: datetime
    description: str = ""
    location: str = ""
    all_day: bool = False

    def format_display(self) -> str:
        """Format for TTS or text display."""
        if self.all_day:
            date_str = self.start.strftime("%A, %B %-d")
            return f"{self.summary} (all day, {date_str})"
        time_str = self.start.strftime("%-I:%M %p")
        end_str = self.end.strftime("%-I:%M %p")
        return f"{self.summary} at {time_str} to {end_str}"


@dataclass(frozen=True)
class EmailMessage:
    """An email message summary from IMAP."""

    message_id: str
    subject: str
    sender: str
    date: datetime
    preview: str = ""  # First ~100 chars of body
    is_read: bool = False

    def format_display(self) -> str:
        """Format for TTS or text display."""
        status = "" if self.is_read else " (unread)"
        return f"From {self.sender}: {self.subject}{status}"


@dataclass(frozen=True)
class ExternalNotification:
    """A notification to send via external provider (ntfy, Pushover, etc.)."""

    message: str
    title: str = ""
    priority: int = 3  # 1=min, 3=default, 5=max
    tags: list[str] = field(default_factory=list)
    topic: str = ""  # Override default topic
