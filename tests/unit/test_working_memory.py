"""Tests for working memory — VoiceSession wrapper."""

from __future__ import annotations

from cortex.memory.working import WorkingMemory
from cortex.voice.types import VoiceSession


class TestWorkingMemoryEmpty:
    def test_no_session(self) -> None:
        wm = WorkingMemory()
        assert wm.session is None
        assert wm.history == []
        assert wm.turn_count == 0

    def test_summary_empty(self) -> None:
        wm = WorkingMemory()
        assert wm.get_summary_text() == ""


class TestWorkingMemoryWithSession:
    def test_attach_session(self) -> None:
        session = VoiceSession()
        wm = WorkingMemory(session=session)
        assert wm.session is session

    def test_history_from_session(self) -> None:
        session = VoiceSession()
        session.history.append({"role": "user", "content": "hello"})
        session.history.append({"role": "assistant", "content": "hi there"})
        wm = WorkingMemory(session=session)
        assert len(wm.history) == 2

    def test_summary_text_format(self) -> None:
        session = VoiceSession()
        session.history.append({"role": "user", "content": "what time is it"})
        session.history.append({"role": "assistant", "content": "It's 3pm"})
        wm = WorkingMemory(session=session)
        summary = wm.get_summary_text()
        assert "User: what time is it" in summary
        assert "Assistant: It's 3pm" in summary

    def test_summary_limits_turns(self) -> None:
        session = VoiceSession()
        for i in range(10):
            session.history.append({"role": "user", "content": f"msg {i}"})
            session.history.append({"role": "assistant", "content": f"reply {i}"})
        wm = WorkingMemory(session=session)
        summary = wm.get_summary_text(max_turns=2)
        # Should only have last 4 messages (2 turns * 2 messages each)
        lines = [line for line in summary.split("\n") if line.strip()]
        assert len(lines) == 4

    def test_clear(self) -> None:
        session = VoiceSession()
        wm = WorkingMemory(session=session)
        wm.clear()
        assert wm.session is None
        assert wm.history == []

    def test_set_session(self) -> None:
        wm = WorkingMemory()
        session = VoiceSession()
        wm.session = session
        assert wm.session is session
