"""Working memory — wraps VoiceSession with rolling summary support.

Working memory is the RAM-only layer that tracks the current conversation.
It provides access to the session history and can produce a summary string
for context assembly (P5 priority).
"""

from __future__ import annotations

from cortex.voice.types import VoiceSession


class WorkingMemory:
    """Working memory layer wrapping a VoiceSession.

    Provides a clean interface for the agent processor and context assembler
    to access the current conversation state.
    """

    def __init__(self, session: VoiceSession | None = None) -> None:
        self._session = session

    @property
    def session(self) -> VoiceSession | None:
        return self._session

    @session.setter
    def session(self, value: VoiceSession | None) -> None:
        self._session = value

    @property
    def history(self) -> list[dict[str, str]]:
        """Get conversation history from current session."""
        if self._session is None:
            return []
        return self._session.history

    @property
    def turn_count(self) -> int:
        """Number of completed turns in the current session."""
        if self._session is None:
            return 0
        return self._session.turn_count

    def get_summary_text(self, max_turns: int = 3) -> str:
        """Build a brief summary of recent conversation for P5 injection.

        Returns the last `max_turns` exchanges formatted as a summary string.
        This is a simple approach — a proper summary would use the LLM.
        """
        history = self.history
        if not history:
            return ""

        recent = history[-(max_turns * 2) :]  # 2 messages per turn
        lines = []
        for msg in recent:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "user":
                lines.append(f"User: {content}")
            elif role == "assistant":
                lines.append(f"Assistant: {content}")
        return "\n".join(lines)

    def clear(self) -> None:
        """Clear working memory (session ended)."""
        self._session = None
