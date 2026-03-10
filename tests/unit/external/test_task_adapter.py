"""Tests for task adapters (mock and CalDAV VTODO parser)."""

from __future__ import annotations

from datetime import UTC, datetime

from cortex.external.protocols import ExternalServiceAdapter
from cortex.external.tasks.caldav_tasks import _build_vtodo
from cortex.external.tasks.mock import MockTaskAdapter
from cortex.external.tasks.types import TaskItem

# --- TaskItem types ---


def _make_task(
    uid: str = "test-1",
    summary: str = "Test Task",
    **kwargs: object,
) -> TaskItem:
    return TaskItem(uid=uid, summary=summary, **kwargs)  # type: ignore[arg-type]


class TestTaskItemTypes:
    def test_format_display_pending(self) -> None:
        task = _make_task(summary="Buy groceries")
        assert "Buy groceries" in task.format_display()
        assert "pending" in task.format_display()

    def test_format_display_completed(self) -> None:
        task = _make_task(summary="Done task", completed=True)
        assert "done" in task.format_display()

    def test_format_display_with_due_date(self) -> None:
        task = _make_task(
            summary="Review PR",
            due_date=datetime(2025, 6, 15, tzinfo=UTC),
        )
        display = task.format_display()
        assert "due" in display
        assert "June" in display

    def test_format_display_no_due_date(self) -> None:
        task = _make_task(summary="Undated task")
        display = task.format_display()
        assert "due" not in display

    def test_default_values(self) -> None:
        task = TaskItem(uid="t1", summary="Test")
        assert task.completed is False
        assert task.due_date is None
        assert task.priority == 0
        assert task.description == ""


# --- MockTaskAdapter Protocol Compliance ---


class TestMockTaskAdapterProtocol:
    def test_satisfies_external_service_adapter(self) -> None:
        adapter = MockTaskAdapter()
        assert isinstance(adapter, ExternalServiceAdapter)

    def test_service_type(self) -> None:
        adapter = MockTaskAdapter()
        assert adapter.service_type == "tasks"


# --- MockTaskAdapter Lifecycle ---


class TestMockTaskAdapterLifecycle:
    async def test_connect(self) -> None:
        adapter = MockTaskAdapter()
        await adapter.connect()
        assert adapter._connected is True

    async def test_disconnect(self) -> None:
        adapter = MockTaskAdapter()
        await adapter.connect()
        await adapter.disconnect()
        assert adapter._connected is False

    async def test_health_check_connected(self) -> None:
        adapter = MockTaskAdapter()
        await adapter.connect()
        assert await adapter.health_check() is True

    async def test_health_check_disconnected(self) -> None:
        adapter = MockTaskAdapter()
        assert await adapter.health_check() is False


# --- MockTaskAdapter CRUD ---


class TestMockTaskAdapterListTasks:
    async def test_list_empty(self) -> None:
        adapter = MockTaskAdapter()
        tasks = await adapter.list_tasks()
        assert tasks == []

    async def test_list_pending_only(self) -> None:
        adapter = MockTaskAdapter()
        await adapter.create_task(_make_task(uid="t1"))
        await adapter.create_task(_make_task(uid="t2", completed=True))

        tasks = await adapter.list_tasks(include_completed=False)
        assert len(tasks) == 1
        assert tasks[0].uid == "t1"

    async def test_list_include_completed(self) -> None:
        adapter = MockTaskAdapter()
        await adapter.create_task(_make_task(uid="t1"))
        await adapter.create_task(_make_task(uid="t2", completed=True))

        tasks = await adapter.list_tasks(include_completed=True)
        assert len(tasks) == 2


class TestMockTaskAdapterCreateTask:
    async def test_create_task(self) -> None:
        adapter = MockTaskAdapter()
        task = _make_task(uid="new-1", summary="New Task")
        result = await adapter.create_task(task)
        assert result.uid == "new-1"
        assert result.summary == "New Task"

    async def test_created_task_appears_in_list(self) -> None:
        adapter = MockTaskAdapter()
        await adapter.create_task(_make_task(uid="created"))
        tasks = await adapter.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].uid == "created"


class TestMockTaskAdapterCompleteTask:
    async def test_complete_existing(self) -> None:
        adapter = MockTaskAdapter()
        await adapter.create_task(_make_task(uid="to-complete"))

        completed = await adapter.complete_task("to-complete")
        assert completed is True

        tasks = await adapter.list_tasks(include_completed=True)
        assert tasks[0].completed is True

    async def test_complete_nonexistent(self) -> None:
        adapter = MockTaskAdapter()
        completed = await adapter.complete_task("nonexistent")
        assert completed is False

    async def test_complete_already_completed(self) -> None:
        adapter = MockTaskAdapter()
        await adapter.create_task(_make_task(uid="done", completed=True))

        completed = await adapter.complete_task("done")
        assert completed is False

    async def test_completed_task_hidden_by_default(self) -> None:
        adapter = MockTaskAdapter()
        await adapter.create_task(_make_task(uid="t1"))
        await adapter.complete_task("t1")

        tasks = await adapter.list_tasks()
        assert len(tasks) == 0

        tasks = await adapter.list_tasks(include_completed=True)
        assert len(tasks) == 1


class TestMockTaskAdapterDeleteTask:
    async def test_delete_existing(self) -> None:
        adapter = MockTaskAdapter()
        await adapter.create_task(_make_task(uid="to-delete"))

        deleted = await adapter.delete_task("to-delete")
        assert deleted is True

        tasks = await adapter.list_tasks(include_completed=True)
        assert len(tasks) == 0

    async def test_delete_nonexistent(self) -> None:
        adapter = MockTaskAdapter()
        deleted = await adapter.delete_task("nonexistent")
        assert deleted is False

    async def test_delete_only_removes_target(self) -> None:
        adapter = MockTaskAdapter()
        await adapter.create_task(_make_task(uid="keep"))
        await adapter.create_task(_make_task(uid="remove"))

        await adapter.delete_task("remove")
        tasks = await adapter.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].uid == "keep"


class TestMockTaskAdapterSampleTasks:
    def test_add_sample_tasks(self) -> None:
        adapter = MockTaskAdapter()
        adapter.add_sample_tasks()
        assert len(adapter._tasks) == 3

    async def test_sample_tasks_filter_completed(self) -> None:
        adapter = MockTaskAdapter()
        adapter.add_sample_tasks()

        pending = await adapter.list_tasks(include_completed=False)
        all_tasks = await adapter.list_tasks(include_completed=True)
        assert len(pending) == 2
        assert len(all_tasks) == 3


# --- CalDAV VTODO builder ---


class TestCalDAVVtodoBuilder:
    def test_build_basic(self) -> None:
        task = TaskItem(uid="test-uid", summary="Buy milk")
        vcal = _build_vtodo(task)
        assert "BEGIN:VCALENDAR" in vcal
        assert "BEGIN:VTODO" in vcal
        assert "UID:test-uid" in vcal
        assert "SUMMARY:Buy milk" in vcal
        assert "STATUS:NEEDS-ACTION" in vcal
        assert "END:VTODO" in vcal
        assert "END:VCALENDAR" in vcal

    def test_build_completed(self) -> None:
        task = TaskItem(uid="done-uid", summary="Done task", completed=True)
        vcal = _build_vtodo(task)
        assert "STATUS:COMPLETED" in vcal

    def test_build_with_due_date(self) -> None:
        task = TaskItem(
            uid="due-uid",
            summary="Due task",
            due_date=datetime(2025, 6, 15, 10, 0, tzinfo=UTC),
        )
        vcal = _build_vtodo(task)
        assert "DUE:20250615T100000Z" in vcal

    def test_build_with_priority(self) -> None:
        task = TaskItem(uid="pri-uid", summary="Important", priority=1)
        vcal = _build_vtodo(task)
        assert "PRIORITY:1" in vcal

    def test_build_no_optional_fields(self) -> None:
        task = TaskItem(uid="min-uid", summary="Minimal")
        vcal = _build_vtodo(task)
        assert "DUE" not in vcal
        assert "PRIORITY" not in vcal
        assert "DESCRIPTION" not in vcal

    def test_build_with_description(self) -> None:
        task = TaskItem(uid="desc-uid", summary="Task", description="Details here")
        vcal = _build_vtodo(task)
        assert "DESCRIPTION:Details here" in vcal
