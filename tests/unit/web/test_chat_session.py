"""Tests for WebChatSession conversation management."""

from __future__ import annotations

from cortex.agent.types import AgentResponse
from cortex.web.chat_session import WebChatSession


class TestWebChatSession:
    """Tests for WebChatSession lifecycle and history."""

    def test_create_session_has_id(self) -> None:
        session = WebChatSession()
        assert len(session.session_id) > 0

    def test_custom_session_id(self) -> None:
        session = WebChatSession(session_id="custom-123")
        assert session.session_id == "custom-123"

    def test_initial_history_empty(self) -> None:
        session = WebChatSession()
        assert session.history == []

    def test_initial_turn_count_zero(self) -> None:
        session = WebChatSession()
        assert session.turn_count == 0

    def test_add_user_message(self) -> None:
        session = WebChatSession()
        session.add_user_message("hello")
        assert len(session.history) == 1
        assert session.history[0] == {"role": "user", "content": "hello"}

    def test_add_user_message_increments_turn_count(self) -> None:
        session = WebChatSession()
        session.add_user_message("first")
        session.add_user_message("second")
        assert session.turn_count == 2

    def test_add_assistant_message(self) -> None:
        session = WebChatSession()
        session.add_assistant_message("hi there")
        assert session.history[-1] == {"role": "assistant", "content": "hi there"}

    def test_process_response_updates_history(self) -> None:
        session = WebChatSession()
        response = AgentResponse(text="The time is 2:30 PM.")
        result = session.process_response(response)
        assert result == "The time is 2:30 PM."
        assert session.history[-1]["role"] == "assistant"

    def test_process_response_empty_text(self) -> None:
        session = WebChatSession()
        response = AgentResponse(text="", used_llm=True)
        result = session.process_response(response)
        assert result == ""
        # Empty text should not be added to history
        assert len(session.history) == 0

    def test_full_conversation_flow(self) -> None:
        session = WebChatSession()
        session.add_user_message("what time is it")
        response = AgentResponse(text="It's 2:30 PM.")
        session.process_response(response)
        session.add_user_message("thanks")
        response2 = AgentResponse(text="You're welcome!")
        session.process_response(response2)

        assert len(session.history) == 4
        assert session.history[0]["role"] == "user"
        assert session.history[1]["role"] == "assistant"
        assert session.history[2]["role"] == "user"
        assert session.history[3]["role"] == "assistant"
        assert session.turn_count == 2

    def test_voice_session_accessible(self) -> None:
        session = WebChatSession()
        assert session.voice_session is not None
        assert session.voice_session.session_id == session.session_id
