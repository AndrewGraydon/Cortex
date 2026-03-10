"""CalDAV task adapter — VTODO read/write via CalDAV server.

Shares the CalDAV server connection with the calendar adapter.
Password is read from the CALDAV_PASSWORD environment variable.
"""

from __future__ import annotations

import contextlib
import os
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from cortex.external.tasks.types import TaskItem

logger = structlog.get_logger()


class CalDAVTaskAdapter:
    """CalDAV VTODO adapter implementing ExternalServiceAdapter protocol.

    Connects to a CalDAV server and manages tasks via VTODO entries.
    """

    def __init__(self, url: str, username: str = "") -> None:
        self._url = url
        self._username = username
        self._client: Any = None
        self._calendar: Any = None
        self._connected = False

    async def connect(self) -> None:
        """Connect to the CalDAV server and select a task-capable calendar."""
        try:
            import caldav  # noqa: PLC0415

            password = os.environ.get("CALDAV_PASSWORD", "")
            self._client = caldav.DAVClient(  # type: ignore[operator]
                url=self._url,
                username=self._username,
                password=password,
            )
            principal = self._client.principal()
            calendars = principal.calendars()
            if calendars:
                self._calendar = calendars[0]
                logger.info(
                    "CalDAV tasks connected",
                    url=self._url,
                    calendar=str(self._calendar),
                )
            else:
                logger.warning("CalDAV connected but no calendars found", url=self._url)
            self._connected = True
        except Exception:
            self._connected = False
            logger.exception("CalDAV task connection failed", url=self._url)
            raise

    async def disconnect(self) -> None:
        """Disconnect from the CalDAV server."""
        self._client = None
        self._calendar = None
        self._connected = False
        logger.info("CalDAV tasks disconnected")

    async def health_check(self) -> bool:
        """Check if we can reach the CalDAV server."""
        if not self._connected or self._client is None:
            return False
        try:
            self._client.principal()
            return True
        except Exception:
            logger.exception("CalDAV task health check failed")
            return False

    @property
    def service_type(self) -> str:
        return "tasks"

    async def list_tasks(self, include_completed: bool = False) -> list[TaskItem]:
        """List tasks from the CalDAV server."""
        if self._calendar is None:
            return []

        try:
            todos = self._calendar.todos(include_completed=include_completed)
            tasks: list[TaskItem] = []
            for todo in todos:
                task = _parse_vtodo(todo)
                if task is not None:
                    tasks.append(task)
            return tasks
        except Exception:
            logger.exception("CalDAV list_tasks failed")
            return []

    async def create_task(self, task: TaskItem) -> TaskItem:
        """Create a task on the CalDAV server."""
        if self._calendar is None:
            msg = "Not connected to a calendar"
            raise RuntimeError(msg)

        vcal = _build_vtodo(task)
        try:
            self._calendar.save_todo(vcal)
            logger.info("CalDAV task created", summary=task.summary, uid=task.uid)
            return task
        except Exception:
            logger.exception("CalDAV create_task failed", summary=task.summary)
            raise

    async def complete_task(self, uid: str) -> bool:
        """Mark a task as completed by UID."""
        if self._calendar is None:
            return False
        try:
            todos = self._calendar.todos(include_completed=False)
            for todo in todos:
                vtodo = todo.vobject_instance.vtodo
                if str(vtodo.uid.value) == uid:
                    todo.complete()
                    logger.info("CalDAV task completed", uid=uid)
                    return True
            return False
        except Exception:
            logger.exception("CalDAV complete_task failed", uid=uid)
            return False

    async def delete_task(self, uid: str) -> bool:
        """Delete a task by UID."""
        if self._calendar is None:
            return False
        try:
            todos = self._calendar.todos(include_completed=True)
            for todo in todos:
                vtodo = todo.vobject_instance.vtodo
                if str(vtodo.uid.value) == uid:
                    todo.delete()
                    logger.info("CalDAV task deleted", uid=uid)
                    return True
            return False
        except Exception:
            logger.exception("CalDAV delete_task failed", uid=uid)
            return False


def _parse_vtodo(raw_todo: Any) -> TaskItem | None:
    """Parse a caldav todo object into a TaskItem."""
    try:
        vtodo = raw_todo.vobject_instance.vtodo
        uid = str(vtodo.uid.value) if hasattr(vtodo, "uid") else uuid.uuid4().hex
        summary = str(vtodo.summary.value) if hasattr(vtodo, "summary") else "Untitled"

        completed = False
        if hasattr(vtodo, "status"):
            completed = str(vtodo.status.value).upper() == "COMPLETED"

        due_date = None
        if hasattr(vtodo, "due"):
            due_val = vtodo.due.value
            if isinstance(due_val, datetime):
                due_date = due_val if due_val.tzinfo else due_val.replace(tzinfo=UTC)
            else:
                due_date = datetime.combine(due_val, datetime.min.time(), tzinfo=UTC)

        priority = 0
        if hasattr(vtodo, "priority"):
            with contextlib.suppress(ValueError, TypeError):
                priority = int(vtodo.priority.value)

        description = ""
        if hasattr(vtodo, "description"):
            description = str(vtodo.description.value)

        return TaskItem(
            uid=uid,
            summary=summary,
            completed=completed,
            due_date=due_date,
            priority=priority,
            description=description,
        )
    except Exception:
        logger.exception("Failed to parse CalDAV todo")
        return None


def _build_vtodo(task: TaskItem) -> str:
    """Build a VCALENDAR string with a VTODO from a TaskItem."""
    uid = task.uid or uuid.uuid4().hex
    status = "COMPLETED" if task.completed else "NEEDS-ACTION"

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Cortex//Tasks//EN",
        "BEGIN:VTODO",
        f"UID:{uid}",
        f"SUMMARY:{task.summary}",
        f"STATUS:{status}",
    ]
    if task.due_date is not None:
        lines.append(f"DUE:{task.due_date.strftime('%Y%m%dT%H%M%SZ')}")
    if task.priority > 0:
        lines.append(f"PRIORITY:{task.priority}")
    if task.description:
        lines.append(f"DESCRIPTION:{task.description}")
    lines.extend(["END:VTODO", "END:VCALENDAR"])
    return "\n".join(lines)
