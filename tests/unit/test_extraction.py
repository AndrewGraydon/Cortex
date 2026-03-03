"""Tests for memory extraction — regex-based fact capture."""

from __future__ import annotations

from cortex.memory.extraction import MemoryExtractor
from cortex.memory.types import MemoryCategory


class TestImmediateExtraction:
    def test_remember_that(self) -> None:
        extractor = MemoryExtractor()
        results = extractor.extract_immediate("remember that my favorite color is blue")
        assert len(results) == 1
        assert "blue" in results[0].content.lower()
        assert results[0].category == MemoryCategory.FACT

    def test_my_name_is(self) -> None:
        extractor = MemoryExtractor()
        results = extractor.extract_immediate("my name is Andrew")
        assert len(results) == 1
        assert "Andrew" in results[0].content
        assert results[0].category == MemoryCategory.PERSON

    def test_name_normalized(self) -> None:
        extractor = MemoryExtractor()
        results = extractor.extract_immediate("my name is Sarah")
        assert results[0].content == "User's name is Sarah"

    def test_i_live_in(self) -> None:
        extractor = MemoryExtractor()
        results = extractor.extract_immediate("I live in Vancouver")
        assert len(results) == 1
        assert "Vancouver" in results[0].content
        assert results[0].category == MemoryCategory.PLACE

    def test_im_from(self) -> None:
        extractor = MemoryExtractor()
        results = extractor.extract_immediate("I'm from Tokyo")
        assert len(results) == 1
        assert "Tokyo" in results[0].content

    def test_i_like(self) -> None:
        extractor = MemoryExtractor()
        results = extractor.extract_immediate("I like coffee")
        assert len(results) == 1
        assert results[0].category == MemoryCategory.PREFERENCE

    def test_i_wake_up_at(self) -> None:
        extractor = MemoryExtractor()
        results = extractor.extract_immediate("I wake up at 7am")
        assert len(results) == 1
        assert results[0].category == MemoryCategory.ROUTINE
        assert "7am" in results[0].content

    def test_no_match(self) -> None:
        extractor = MemoryExtractor()
        results = extractor.extract_immediate("tell me about black holes")
        assert len(results) == 0

    def test_short_fact_rejected(self) -> None:
        extractor = MemoryExtractor()
        # "my name is X" where X is too short
        results = extractor.extract_immediate("my name is")
        assert len(results) == 0

    def test_confidence_is_high(self) -> None:
        extractor = MemoryExtractor()
        results = extractor.extract_immediate("remember that I need to buy milk")
        assert len(results) == 1
        assert results[0].confidence == 0.9

    def test_entry_has_id_and_timestamp(self) -> None:
        extractor = MemoryExtractor()
        results = extractor.extract_immediate("my name is Andrew")
        assert len(results[0].id) == 16
        assert results[0].created_at > 0


class TestConversationExtraction:
    def test_extract_from_history(self) -> None:
        extractor = MemoryExtractor()
        history = [
            {"role": "user", "content": "my name is Andrew"},
            {"role": "assistant", "content": "Nice to meet you, Andrew!"},
            {"role": "user", "content": "I live in Vancouver"},
            {"role": "assistant", "content": "Vancouver is a great city!"},
        ]
        results = extractor.extract_from_conversation(history, session_id="s1")
        assert len(results) == 2
        assert all(r.source_conversation == "s1" for r in results)

    def test_dedup_in_conversation(self) -> None:
        extractor = MemoryExtractor()
        history = [
            {"role": "user", "content": "my name is Andrew"},
            {"role": "assistant", "content": "Got it."},
            {"role": "user", "content": "my name is Andrew"},
        ]
        results = extractor.extract_from_conversation(history)
        # Same content should be deduplicated
        assert len(results) == 1

    def test_skips_assistant_messages(self) -> None:
        extractor = MemoryExtractor()
        history = [
            {"role": "assistant", "content": "remember that you asked about this"},
            {"role": "user", "content": "what time is it"},
        ]
        results = extractor.extract_from_conversation(history)
        assert len(results) == 0

    def test_empty_history(self) -> None:
        extractor = MemoryExtractor()
        results = extractor.extract_from_conversation([])
        assert len(results) == 0
