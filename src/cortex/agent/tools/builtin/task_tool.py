"""Task tools — query, create, and complete tasks. Tier 0/1.

Wired to a task adapter backend. Falls back to stub responses
if no backend is configured.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from cortex.agent.types import ToolResult
from cortex.external.tasks.types import TaskItem

logger = logging.getLogger(__name__)

# Module-level backend — set via set_task_backend()
_adapter: Any = None


def set_task_backend(adapter: Any) -> None:
    """Wire the task tools to a real or mock adapter."""
    global _adapter  # noqa: PLW0603
    _adapter = adapter


def get_task_backend() -> Any:
    """Get the current task backend (for testing)."""
    return _adapter


class TaskQueryTool:
    """Query pending tasks. Tier 0 (safe, read-only)."""

    @property
    def name(self) -> str:
        return "task_query"

    @property
    def description(self) -> str:
        return "List pending tasks"

    @property
    def permission_tier(self) -> int:
        return 0

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "task_query",
            "description": "List pending tasks",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_completed": {
                        "type": "boolean",
                        "description": "Include completed tasks (default false)",
                    },
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if _adapter is None:
            return ToolResult(
                tool_name="task_query",
                success=True,
                data=[],
                display_text="Tasks are not configured.",
            )

        include_completed = arguments.get("include_completed", False)

        try:
            tasks = await _adapter.list_tasks(include_completed=include_completed)

            if not tasks:
                return ToolResult(
                    tool_name="task_query",
                    success=True,
                    data=[],
                    display_text="You have no pending tasks.",
                )

            data = [
                {
                    "uid": t.uid,
                    "summary": t.summary,
                    "completed": t.completed,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "priority": t.priority,
                }
                for t in tasks
            ]

            if len(tasks) == 1:
                display = f"You have 1 task: {tasks[0].format_display()}."
            else:
                items = [t.format_display() for t in tasks[:5]]
                display = f"You have {len(tasks)} tasks. " + ". ".join(items) + "."

            return ToolResult(
                tool_name="task_query",
                success=True,
                data=data,
                display_text=display,
            )
        except Exception as e:
            logger.exception("Task query failed")
            return ToolResult(
                tool_name="task_query",
                success=False,
                error=str(e),
            )


class TaskCreateTool:
    """Create a new task. Tier 1 (normal, logged)."""

    @property
    def name(self) -> str:
        return "task_create"

    @property
    def description(self) -> str:
        return "Create a new task"

    @property
    def permission_tier(self) -> int:
        return 1

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "task_create",
            "description": "Create a new task",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Task title",
                    },
                    "due_days": {
                        "type": "integer",
                        "description": "Days from now until due (optional)",
                    },
                    "priority": {
                        "type": "integer",
                        "description": "Priority 1-9, 1=highest (optional)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Task description (optional)",
                    },
                },
                "required": ["summary"],
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if _adapter is None:
            return ToolResult(
                tool_name="task_create",
                success=False,
                error="Tasks are not configured.",
            )

        summary = arguments.get("summary", "").strip()
        if not summary:
            return ToolResult(
                tool_name="task_create",
                success=False,
                error="Task summary is required.",
            )

        due_date = None
        due_days = arguments.get("due_days")
        if isinstance(due_days, int) and due_days > 0:
            due_date = datetime.now(tz=UTC) + timedelta(days=due_days)

        priority = arguments.get("priority", 0)
        if not isinstance(priority, int) or priority < 0 or priority > 9:
            priority = 0

        task = TaskItem(
            uid=uuid.uuid4().hex,
            summary=summary,
            due_date=due_date,
            priority=priority,
            description=arguments.get("description", ""),
        )

        try:
            created = await _adapter.create_task(task)
            return ToolResult(
                tool_name="task_create",
                success=True,
                data={
                    "uid": created.uid,
                    "summary": created.summary,
                    "due_date": created.due_date.isoformat() if created.due_date else None,
                },
                display_text=f"Created task: {created.summary}.",
            )
        except Exception as e:
            logger.exception("Task create failed")
            return ToolResult(
                tool_name="task_create",
                success=False,
                error=str(e),
            )


class TaskCompleteTool:
    """Mark a task as completed. Tier 1 (normal, logged)."""

    @property
    def name(self) -> str:
        return "task_complete"

    @property
    def description(self) -> str:
        return "Mark a task as completed"

    @property
    def permission_tier(self) -> int:
        return 1

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "task_complete",
            "description": "Mark a task as completed",
            "parameters": {
                "type": "object",
                "properties": {
                    "uid": {
                        "type": "string",
                        "description": "Task UID to complete",
                    },
                },
                "required": ["uid"],
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if _adapter is None:
            return ToolResult(
                tool_name="task_complete",
                success=False,
                error="Tasks are not configured.",
            )

        uid = arguments.get("uid", "").strip()
        if not uid:
            return ToolResult(
                tool_name="task_complete",
                success=False,
                error="Task UID is required.",
            )

        try:
            completed = await _adapter.complete_task(uid)
            if completed:
                return ToolResult(
                    tool_name="task_complete",
                    success=True,
                    data={"uid": uid},
                    display_text="Task marked as completed.",
                )
            return ToolResult(
                tool_name="task_complete",
                success=False,
                error="Task not found.",
            )
        except Exception as e:
            logger.exception("Task complete failed")
            return ToolResult(
                tool_name="task_complete",
                success=False,
                error=str(e),
            )
