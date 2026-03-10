"""Tests for task tools (query, create, complete)."""

from __future__ import annotations

import pytest

from cortex.agent.tools.builtin.task_tool import (
    TaskCompleteTool,
    TaskCreateTool,
    TaskQueryTool,
    get_task_backend,
    set_task_backend,
)
from cortex.external.tasks.mock import MockTaskAdapter
from cortex.external.tasks.types import TaskItem


@pytest.fixture(autouse=True)
def _reset_backend() -> None:  # type: ignore[misc]
    """Reset the task backend between tests."""
    set_task_backend(None)
    yield  # type: ignore[misc]
    set_task_backend(None)


# --- TaskQueryTool ---


class TestTaskQueryToolSchema:
    def test_name(self) -> None:
        tool = TaskQueryTool()
        assert tool.name == "task_query"

    def test_tier(self) -> None:
        tool = TaskQueryTool()
        assert tool.permission_tier == 0

    def test_schema(self) -> None:
        tool = TaskQueryTool()
        schema = tool.get_schema()
        assert schema["name"] == "task_query"


class TestTaskQueryToolNoBackend:
    async def test_no_backend_returns_not_configured(self) -> None:
        tool = TaskQueryTool()
        result = await tool.execute({})
        assert result.success is True
        assert "not configured" in result.display_text


class TestTaskQueryToolWithBackend:
    async def test_empty_list(self) -> None:
        adapter = MockTaskAdapter()
        set_task_backend(adapter)

        tool = TaskQueryTool()
        result = await tool.execute({})
        assert result.success is True
        assert "no pending tasks" in result.display_text.lower()

    async def test_list_tasks(self) -> None:
        adapter = MockTaskAdapter()
        await adapter.create_task(TaskItem(uid="t1", summary="Buy milk"))
        await adapter.create_task(TaskItem(uid="t2", summary="Walk dog"))
        set_task_backend(adapter)

        tool = TaskQueryTool()
        result = await tool.execute({})
        assert result.success is True
        assert len(result.data) == 2
        assert "2 tasks" in result.display_text

    async def test_single_task_display(self) -> None:
        adapter = MockTaskAdapter()
        await adapter.create_task(TaskItem(uid="t1", summary="Buy milk"))
        set_task_backend(adapter)

        tool = TaskQueryTool()
        result = await tool.execute({})
        assert "1 task" in result.display_text
        assert "Buy milk" in result.display_text

    async def test_include_completed(self) -> None:
        adapter = MockTaskAdapter()
        await adapter.create_task(TaskItem(uid="t1", summary="Done", completed=True))
        set_task_backend(adapter)

        tool = TaskQueryTool()
        # Without include_completed — no pending tasks
        result = await tool.execute({})
        assert "no pending tasks" in result.display_text.lower()

        # With include_completed
        result = await tool.execute({"include_completed": True})
        assert len(result.data) == 1

    async def test_data_structure(self) -> None:
        adapter = MockTaskAdapter()
        from datetime import UTC, datetime, timedelta

        await adapter.create_task(
            TaskItem(
                uid="t1",
                summary="Test",
                due_date=datetime.now(tz=UTC) + timedelta(days=1),
                priority=3,
            )
        )
        set_task_backend(adapter)

        tool = TaskQueryTool()
        result = await tool.execute({})
        item = result.data[0]
        assert "uid" in item
        assert "summary" in item
        assert "completed" in item
        assert "due_date" in item
        assert "priority" in item

    async def test_backend_error(self) -> None:
        class FailingAdapter:
            async def list_tasks(self, **kwargs: object) -> None:
                msg = "DB error"
                raise RuntimeError(msg)

        set_task_backend(FailingAdapter())
        tool = TaskQueryTool()
        result = await tool.execute({})
        assert result.success is False


# --- TaskCreateTool ---


class TestTaskCreateToolSchema:
    def test_name(self) -> None:
        tool = TaskCreateTool()
        assert tool.name == "task_create"

    def test_tier(self) -> None:
        tool = TaskCreateTool()
        assert tool.permission_tier == 1

    def test_schema_required_fields(self) -> None:
        tool = TaskCreateTool()
        schema = tool.get_schema()
        assert "summary" in schema["parameters"]["required"]


class TestTaskCreateToolNoBackend:
    async def test_no_backend_returns_error(self) -> None:
        tool = TaskCreateTool()
        result = await tool.execute({"summary": "test"})
        assert result.success is False
        assert "not configured" in (result.error or "")


class TestTaskCreateToolWithBackend:
    async def test_create_basic(self) -> None:
        adapter = MockTaskAdapter()
        set_task_backend(adapter)

        tool = TaskCreateTool()
        result = await tool.execute({"summary": "Buy milk"})
        assert result.success is True
        assert result.data["summary"] == "Buy milk"
        assert "Created task" in result.display_text

    async def test_create_with_due_days(self) -> None:
        adapter = MockTaskAdapter()
        set_task_backend(adapter)

        tool = TaskCreateTool()
        result = await tool.execute({"summary": "Review PR", "due_days": 3})
        assert result.success is True
        assert result.data["due_date"] is not None

    async def test_create_with_priority(self) -> None:
        adapter = MockTaskAdapter()
        set_task_backend(adapter)

        tool = TaskCreateTool()
        result = await tool.execute({"summary": "Urgent", "priority": 1})
        assert result.success is True

        tasks = await adapter.list_tasks()
        assert tasks[0].priority == 1

    async def test_empty_summary_rejected(self) -> None:
        adapter = MockTaskAdapter()
        set_task_backend(adapter)

        tool = TaskCreateTool()
        result = await tool.execute({"summary": ""})
        assert result.success is False
        assert "required" in (result.error or "")

    async def test_missing_summary_rejected(self) -> None:
        adapter = MockTaskAdapter()
        set_task_backend(adapter)

        tool = TaskCreateTool()
        result = await tool.execute({})
        assert result.success is False

    async def test_invalid_priority_defaults_to_zero(self) -> None:
        adapter = MockTaskAdapter()
        set_task_backend(adapter)

        tool = TaskCreateTool()
        await tool.execute({"summary": "Test", "priority": -5})
        tasks = await adapter.list_tasks()
        assert tasks[0].priority == 0

    async def test_backend_error(self) -> None:
        class FailingAdapter:
            async def create_task(self, task: object) -> None:
                msg = "Write error"
                raise RuntimeError(msg)

        set_task_backend(FailingAdapter())
        tool = TaskCreateTool()
        result = await tool.execute({"summary": "test"})
        assert result.success is False


# --- TaskCompleteTool ---


class TestTaskCompleteToolSchema:
    def test_name(self) -> None:
        tool = TaskCompleteTool()
        assert tool.name == "task_complete"

    def test_tier(self) -> None:
        tool = TaskCompleteTool()
        assert tool.permission_tier == 1


class TestTaskCompleteToolNoBackend:
    async def test_no_backend_returns_error(self) -> None:
        tool = TaskCompleteTool()
        result = await tool.execute({"uid": "test"})
        assert result.success is False


class TestTaskCompleteToolWithBackend:
    async def test_complete_existing(self) -> None:
        adapter = MockTaskAdapter()
        await adapter.create_task(TaskItem(uid="t1", summary="Test"))
        set_task_backend(adapter)

        tool = TaskCompleteTool()
        result = await tool.execute({"uid": "t1"})
        assert result.success is True
        assert "completed" in result.display_text.lower()

    async def test_complete_nonexistent(self) -> None:
        adapter = MockTaskAdapter()
        set_task_backend(adapter)

        tool = TaskCompleteTool()
        result = await tool.execute({"uid": "missing"})
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    async def test_empty_uid_rejected(self) -> None:
        adapter = MockTaskAdapter()
        set_task_backend(adapter)

        tool = TaskCompleteTool()
        result = await tool.execute({"uid": ""})
        assert result.success is False
        assert "required" in (result.error or "")

    async def test_missing_uid_rejected(self) -> None:
        adapter = MockTaskAdapter()
        set_task_backend(adapter)

        tool = TaskCompleteTool()
        result = await tool.execute({})
        assert result.success is False

    async def test_set_get_backend(self) -> None:
        adapter = MockTaskAdapter()
        set_task_backend(adapter)
        assert get_task_backend() is adapter
