"""Mock task adapter — in-memory task store for testing and offline use."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from cortex.external.tasks.types import TaskItem

logger = logging.getLogger(__name__)


class MockTaskAdapter:
    """In-memory task adapter for testing and development.

    Stores tasks in a list. No real CalDAV server required.
    Satisfies ExternalServiceAdapter protocol.
    """

    def __init__(self) -> None:
        self._tasks: list[TaskItem] = []
        self._connected = False

    async def connect(self) -> None:
        self._connected = True
        logger.info("MockTaskAdapter connected")

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("MockTaskAdapter disconnected")

    async def health_check(self) -> bool:
        return self._connected

    @property
    def service_type(self) -> str:
        return "tasks"

    async def list_tasks(self, include_completed: bool = False) -> list[TaskItem]:
        """List tasks, optionally including completed ones."""
        if include_completed:
            return list(self._tasks)
        return [t for t in self._tasks if not t.completed]

    async def create_task(self, task: TaskItem) -> TaskItem:
        """Add a task to the store."""
        self._tasks.append(task)
        logger.info("MockTaskAdapter created task: %s", task.summary)
        return task

    async def complete_task(self, uid: str) -> bool:
        """Mark a task as completed by UID."""
        for i, task in enumerate(self._tasks):
            if task.uid == uid and not task.completed:
                self._tasks[i] = TaskItem(
                    uid=task.uid,
                    summary=task.summary,
                    completed=True,
                    due_date=task.due_date,
                    priority=task.priority,
                    description=task.description,
                )
                logger.info("MockTaskAdapter completed task: %s", uid)
                return True
        return False

    async def delete_task(self, uid: str) -> bool:
        """Delete a task by UID."""
        before = len(self._tasks)
        self._tasks = [t for t in self._tasks if t.uid != uid]
        deleted = len(self._tasks) < before
        if deleted:
            logger.info("MockTaskAdapter deleted task: %s", uid)
        return deleted

    def add_sample_tasks(self) -> None:
        """Populate with sample tasks for development/testing."""
        now = datetime.now(tz=UTC)
        samples = [
            TaskItem(
                uid="mock-task-1",
                summary="Buy groceries",
                due_date=now + timedelta(days=1),
                priority=1,
            ),
            TaskItem(
                uid="mock-task-2",
                summary="Review pull request",
                due_date=now + timedelta(hours=4),
                priority=3,
            ),
            TaskItem(
                uid="mock-task-3",
                summary="Call dentist",
                completed=True,
            ),
        ]
        self._tasks.extend(samples)
