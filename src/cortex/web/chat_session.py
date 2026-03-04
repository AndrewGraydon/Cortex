"""Web chat session — bridges WebSocket clients to AgentProcessor.

Each browser tab creates a WebChatSession that wraps a VoiceSession
(same conversation history format) and routes text through AgentProcessor.
"""

from __future__ import annotations

import logging
import uuid

from cortex.agent.types import AgentResponse
from cortex.voice.types import VoiceSession

logger = logging.getLogger(__name__)


class WebChatSession:
    """Manages a single web chat conversation.

    Wraps VoiceSession to reuse the conversation history format,
    so AgentProcessor treats web and voice identically.
    """

    def __init__(self, session_id: str | None = None) -> None:
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.voice_session = VoiceSession(session_id=self.session_id)

    def add_user_message(self, text: str) -> None:
        """Record a user message in the conversation history."""
        self.voice_session.history.append({"role": "user", "content": text})
        self.voice_session.turn_count += 1
        self.voice_session.touch()

    def add_assistant_message(self, text: str) -> None:
        """Record an assistant response in the conversation history."""
        self.voice_session.history.append({"role": "assistant", "content": text})

    def process_response(self, response: AgentResponse) -> str:
        """Process an AgentResponse and update history.

        Returns the response text.
        """
        text = response.text or ""
        if text:
            self.add_assistant_message(text)
        return text

    @property
    def history(self) -> list[dict[str, str]]:
        return self.voice_session.history

    @property
    def turn_count(self) -> int:
        return self.voice_session.turn_count
