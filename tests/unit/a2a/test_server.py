"""Tests for A2A server — JSON-RPC task handling."""

from __future__ import annotations

from cortex.a2a.server import A2aServer


class TestSendTask:
    async def test_send_basic_task(self) -> None:
        server = A2aServer()
        result = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "id": "1",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "Hello"}],
                    },
                },
            }
        )
        assert "result" in result
        assert result["result"]["status"]["state"] == "completed"

    async def test_send_task_with_id(self) -> None:
        server = A2aServer()
        result = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "id": "1",
                "params": {
                    "id": "custom-task-id",
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "Test"}],
                    },
                },
            }
        )
        assert result["result"]["id"] == "custom-task-id"

    async def test_send_task_stores_in_memory(self) -> None:
        server = A2aServer()
        await server.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "id": "1",
                "params": {
                    "id": "stored-task",
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "Store me"}],
                    },
                },
            }
        )
        assert "stored-task" in server.tasks

    async def test_send_task_with_process_fn(self) -> None:
        async def process(text: str) -> str:
            return f"Processed: {text}"

        server = A2aServer(process_fn=process)
        result = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "id": "1",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "Hello world"}],
                    },
                },
            }
        )
        task = result["result"]
        assert task["status"]["state"] == "completed"
        # Check agent response
        messages = task["history"]
        assert len(messages) == 2
        assert messages[1]["role"] == "agent"
        assert "Processed: Hello world" in messages[1]["parts"][0]["text"]

    async def test_send_task_process_fn_failure(self) -> None:
        async def failing_process(text: str) -> str:
            msg = "Processing failed"
            raise RuntimeError(msg)

        server = A2aServer(process_fn=failing_process)
        result = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "id": "1",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "Fail"}],
                    },
                },
            }
        )
        assert result["result"]["status"]["state"] == "failed"

    async def test_send_includes_user_message(self) -> None:
        server = A2aServer()
        result = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "id": "1",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "My message"}],
                    },
                },
            }
        )
        history = result["result"]["history"]
        assert history[0]["role"] == "user"
        assert history[0]["parts"][0]["text"] == "My message"


class TestGetTask:
    async def test_get_existing_task(self) -> None:
        server = A2aServer()
        await server.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "id": "1",
                "params": {
                    "id": "get-me",
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "Test"}],
                    },
                },
            }
        )
        result = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "tasks/get",
                "id": "2",
                "params": {"id": "get-me"},
            }
        )
        assert result["result"]["id"] == "get-me"

    async def test_get_nonexistent_task(self) -> None:
        server = A2aServer()
        result = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "tasks/get",
                "id": "1",
                "params": {"id": "nonexistent"},
            }
        )
        assert "error" in result["result"]


class TestCancelTask:
    async def test_cancel_existing_task(self) -> None:
        server = A2aServer()
        await server.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "id": "1",
                "params": {
                    "id": "cancel-me",
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "Test"}],
                    },
                },
            }
        )
        result = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "tasks/cancel",
                "id": "2",
                "params": {"id": "cancel-me"},
            }
        )
        assert result["result"]["status"]["state"] == "canceled"

    async def test_cancel_nonexistent_task(self) -> None:
        server = A2aServer()
        result = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "tasks/cancel",
                "id": "1",
                "params": {"id": "nonexistent"},
            }
        )
        assert "error" in result["result"]


class TestUnknownMethod:
    async def test_unknown_method_returns_error(self) -> None:
        server = A2aServer()
        result = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "unknown/method",
                "id": "1",
                "params": {},
            }
        )
        assert "error" in result
        assert result["error"]["code"] == -32601


class TestJsonRpcFormat:
    async def test_response_has_jsonrpc_field(self) -> None:
        server = A2aServer()
        result = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "tasks/send",
                "id": "42",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": "Test"}],
                    },
                },
            }
        )
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == "42"

    async def test_error_response_format(self) -> None:
        server = A2aServer()
        result = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "invalid",
                "id": "99",
            }
        )
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == "99"
        assert "error" in result
        assert "code" in result["error"]
        assert "message" in result["error"]
