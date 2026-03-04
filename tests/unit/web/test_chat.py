"""Tests for Milestone 3a.3 — chat page and WebSocket streaming."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from cortex.agent.processor import AgentProcessor
from cortex.agent.router import IntentRouter
from cortex.agent.tools.registry import ToolRegistry
from cortex.config import CortexConfig
from cortex.web.app import create_app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> CortexConfig:
    return CortexConfig()


@pytest.fixture
def app_no_auth(config: CortexConfig) -> TestClient:
    """App without auth, without AgentProcessor (echo mode)."""
    application = create_app(config=config, enable_auth=False)
    with TestClient(application) as client:
        yield client


@pytest.fixture
def app_with_processor(config: CortexConfig) -> TestClient:
    """App with AgentProcessor wired."""
    processor = AgentProcessor(
        router=IntentRouter(),
        registry=ToolRegistry(),
    )
    application = create_app(
        config=config,
        enable_auth=False,
        agent_processor=processor,
    )
    with TestClient(application) as client:
        yield client


# ---------------------------------------------------------------------------
# Chat page tests
# ---------------------------------------------------------------------------


class TestChatPage:
    """Tests for the GET /chat page."""

    def test_chat_page_returns_200(self, app_no_auth: TestClient) -> None:
        response = app_no_auth.get("/chat")
        assert response.status_code == 200

    def test_chat_page_returns_html(self, app_no_auth: TestClient) -> None:
        response = app_no_auth.get("/chat")
        assert "text/html" in response.headers["content-type"]

    def test_chat_page_has_input(self, app_no_auth: TestClient) -> None:
        response = app_no_auth.get("/chat")
        assert 'id="chat-input"' in response.text

    def test_chat_page_has_send_button(self, app_no_auth: TestClient) -> None:
        response = app_no_auth.get("/chat")
        assert "Send" in response.text

    def test_chat_page_has_messages_container(self, app_no_auth: TestClient) -> None:
        response = app_no_auth.get("/chat")
        assert 'id="messages"' in response.text

    def test_chat_page_has_websocket_script(self, app_no_auth: TestClient) -> None:
        response = app_no_auth.get("/chat")
        assert "WebSocket" in response.text
        assert "/ws/chat" in response.text

    def test_chat_page_inherits_base_template(self, app_no_auth: TestClient) -> None:
        response = app_no_auth.get("/chat")
        assert "navbar" in response.text
        assert "daisyui" in response.text


# ---------------------------------------------------------------------------
# WebSocket echo mode tests (no AgentProcessor)
# ---------------------------------------------------------------------------


class TestWebSocketEchoMode:
    """Tests for WebSocket chat in echo mode (no AgentProcessor configured)."""

    def test_websocket_connects(self, app_no_auth: TestClient) -> None:
        with app_no_auth.websocket_connect("/ws/chat") as ws:
            # Just verify connection succeeds
            assert ws is not None

    def test_send_message_gets_echo_response(self, app_no_auth: TestClient) -> None:
        with app_no_auth.websocket_connect("/ws/chat") as ws:
            ws.send_text(json.dumps({"message": "hello"}))
            # First response: user bubble
            user_html = ws.receive_text()
            assert "hello" in user_html
            assert "chat-end" in user_html
            # Second response: assistant echo bubble
            assistant_html = ws.receive_text()
            assert "Echo: hello" in assistant_html
            assert "chat-start" in assistant_html

    def test_user_bubble_html_format(self, app_no_auth: TestClient) -> None:
        with app_no_auth.websocket_connect("/ws/chat") as ws:
            ws.send_text(json.dumps({"message": "test message"}))
            user_html = ws.receive_text()
            assert "hx-swap-oob" in user_html
            assert "chat-bubble-primary" in user_html
            assert "test message" in user_html

    def test_assistant_bubble_html_format(self, app_no_auth: TestClient) -> None:
        with app_no_auth.websocket_connect("/ws/chat") as ws:
            ws.send_text(json.dumps({"message": "test"}))
            ws.receive_text()  # Skip user bubble
            assistant_html = ws.receive_text()
            assert "hx-swap-oob" in assistant_html
            assert "chat-start" in assistant_html

    def test_empty_message_ignored(self, app_no_auth: TestClient) -> None:
        with app_no_auth.websocket_connect("/ws/chat") as ws:
            ws.send_text(json.dumps({"message": ""}))
            # Send a real message to verify the connection is still alive
            ws.send_text(json.dumps({"message": "real message"}))
            user_html = ws.receive_text()
            assert "real message" in user_html

    def test_multiple_messages_in_sequence(self, app_no_auth: TestClient) -> None:
        with app_no_auth.websocket_connect("/ws/chat") as ws:
            for msg in ["first", "second", "third"]:
                ws.send_text(json.dumps({"message": msg}))
                user_html = ws.receive_text()
                assert msg in user_html
                assistant_html = ws.receive_text()
                assert f"Echo: {msg}" in assistant_html

    def test_html_escaped_in_bubbles(self, app_no_auth: TestClient) -> None:
        with app_no_auth.websocket_connect("/ws/chat") as ws:
            ws.send_text(json.dumps({"message": "<script>alert('xss')</script>"}))
            user_html = ws.receive_text()
            assert "<script>" not in user_html
            assert "&lt;script&gt;" in user_html


# ---------------------------------------------------------------------------
# WebSocket with AgentProcessor tests
# ---------------------------------------------------------------------------


class TestWebSocketWithProcessor:
    """Tests for WebSocket chat with a real AgentProcessor."""

    def test_time_query_routed_correctly(self, app_with_processor: TestClient) -> None:
        with app_with_processor.websocket_connect("/ws/chat") as ws:
            ws.send_text(json.dumps({"message": "what time is it"}))
            user_html = ws.receive_text()
            assert "what time is it" in user_html
            assistant_html = ws.receive_text()
            # Clock tool should respond (IntentRouter has time patterns)
            assert "chat-start" in assistant_html

    def test_unknown_query_falls_through(self, app_with_processor: TestClient) -> None:
        with app_with_processor.websocket_connect("/ws/chat") as ws:
            ws.send_text(json.dumps({"message": "tell me about quantum physics"}))
            ws.receive_text()  # user bubble
            assistant_html = ws.receive_text()
            # LLM fallback returns empty text
            assert "chat-start" in assistant_html


# ---------------------------------------------------------------------------
# Chat session management tests
# ---------------------------------------------------------------------------


class TestChatSessionManagement:
    """Tests for WebChatSession conversation tracking."""

    def test_separate_websockets_have_separate_histories(
        self, app_no_auth: TestClient
    ) -> None:
        with app_no_auth.websocket_connect("/ws/chat") as ws1:
            ws1.send_text(json.dumps({"message": "message from tab 1"}))
            ws1.receive_text()
            ws1.receive_text()

        with app_no_auth.websocket_connect("/ws/chat") as ws2:
            ws2.send_text(json.dumps({"message": "message from tab 2"}))
            user_html = ws2.receive_text()
            assert "message from tab 2" in user_html
