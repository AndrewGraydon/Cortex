"""Task data types — task items for CalDAV VTODO sync."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TaskItem:
    """A task/to-do item from any task provider."""

    uid: str
    summary: str
    completed: bool = False
    due_date: datetime | None = None
    priority: int = 0  # 0=unset, 1=highest, 9=lowest (iCalendar convention)
    description: str = ""

    def format_display(self) -> str:
        """Format for TTS or text display."""
        status = "done" if self.completed else "pending"
        parts = [f"{self.summary} ({status})"]
        if self.due_date is not None:
            parts.append(f"due {self.due_date.strftime('%A, %B %-d')}")
        return ", ".join(parts)
