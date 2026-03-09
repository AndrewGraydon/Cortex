"""A2A server — receives and processes tasks from external agents via JSON-RPC."""

from __future__ import annotations

import logging
from typing import Any

from cortex.a2a.types import (
    A2aMessage,
    A2aTask,
    JsonRpcRequest,
    JsonRpcResponse,
    TaskState,
)

logger = logging.getLogger(__name__)


class A2aServer:
    """A2A task server — handles incoming tasks via JSON-RPC.

    Stores tasks in memory (for Phase 3b). A durable store can be added later.
    """

    def __init__(self, process_fn: Any = None) -> None:
        """Initialize the A2A server.

        Args:
            process_fn: Async callable (text) -> str to process incoming tasks.
                       If None, returns a stub response.
        """
        self._tasks: dict[str, A2aTask] = {}
        self._process_fn = process_fn

    @property
    def tasks(self) -> dict[str, A2aTask]:
        return dict(self._tasks)

    async def handle_request(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle a JSON-RPC request and return a response."""
        request = JsonRpcRequest.from_dict(data)

        handlers = {
            "tasks/send": self._handle_send,
            "tasks/get": self._handle_get,
            "tasks/cancel": self._handle_cancel,
        }

        handler = handlers.get(request.method)
        if handler is None:
            return JsonRpcResponse(
                id=request.id,
                error={
                    "code": -32601,
                    "message": f"Method not found: {request.method}",
                },
            ).to_dict()

        try:
            result = await handler(request)
            return JsonRpcResponse(id=request.id, result=result).to_dict()
        except Exception as e:
            logger.exception("A2A request failed: %s", request.method)
            return JsonRpcResponse(
                id=request.id,
                error={"code": -32603, "message": str(e)},
            ).to_dict()

    async def _handle_send(self, request: JsonRpcRequest) -> dict[str, Any]:
        """Handle tasks/send — create and process a new task."""
        params = request.params
        task_id = params.get("id")

        # Extract the user message
        message_data = params.get("message", {})
        parts = message_data.get("parts", [])
        text = ""
        for part in parts:
            if part.get("type") == "text":
                text = part.get("text", "")
                break

        if not text:
            # Check if text is directly in params
            text = params.get("text", "")

        # Create task
        task = A2aTask(id=task_id) if task_id else A2aTask()
        task.messages.append(
            A2aMessage(
                role="user",
                parts=[{"type": "text", "text": text}],
            )
        )
        self._tasks[task.id] = task

        # Process the task
        if self._process_fn and text:
            task.state = TaskState.WORKING
            try:
                response_text = await self._process_fn(text)
                task.messages.append(
                    A2aMessage(
                        role="agent",
                        parts=[{"type": "text", "text": response_text}],
                    )
                )
                task.state = TaskState.COMPLETED
            except Exception:
                logger.exception("A2A task processing failed")
                task.state = TaskState.FAILED
        else:
            task.state = TaskState.COMPLETED
            task.messages.append(
                A2aMessage(
                    role="agent",
                    parts=[{"type": "text", "text": "Task received."}],
                )
            )

        return task.to_dict()

    async def _handle_get(self, request: JsonRpcRequest) -> dict[str, Any]:
        """Handle tasks/get — return task status."""
        task_id = request.params.get("id", "")
        task = self._tasks.get(task_id)
        if task is None:
            return {"error": f"Task not found: {task_id}"}
        return task.to_dict()

    async def _handle_cancel(self, request: JsonRpcRequest) -> dict[str, Any]:
        """Handle tasks/cancel — cancel a task."""
        task_id = request.params.get("id", "")
        task = self._tasks.get(task_id)
        if task is None:
            return {"error": f"Task not found: {task_id}"}
        task.state = TaskState.CANCELED
        return task.to_dict()
