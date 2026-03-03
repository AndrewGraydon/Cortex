"""Tests for memory system data types."""

from __future__ import annotations

import numpy as np

from cortex.memory.types import (
    ConversationSummary,
    MemoryCategory,
    MemoryEntry,
    SearchResult,
)


class TestMemoryCategory:
    def test_all_categories_exist(self) -> None:
        expected = {"fact", "preference", "person", "place", "routine"}
        actual = {c.value for c in MemoryCategory}
        assert actual == expected


class TestMemoryEntry:
    def test_minimal_entry(self) -> None:
        entry = MemoryEntry(
            id="mem-001",
            content="User's name is Andrew",
            category=MemoryCategory.FACT,
        )
        assert entry.id == "mem-001"
        assert entry.embedding is None
        assert entry.confidence == 1.0
        assert entry.superseded_by is None

    def test_with_embedding(self) -> None:
        embedding = np.random.randn(384).astype(np.float32)
        entry = MemoryEntry(
            id="mem-002",
            content="User prefers 22°C",
            category=MemoryCategory.PREFERENCE,
            embedding=embedding,
            source_conversation="sess-abc",
        )
        assert entry.embedding is not None
        assert entry.embedding.shape == (384,)
        assert entry.source_conversation == "sess-abc"

    def test_superseded_entry(self) -> None:
        old = MemoryEntry(
            id="mem-001",
            content="User lives in Toronto",
            category=MemoryCategory.PLACE,
            superseded_by="mem-005",
        )
        assert old.superseded_by == "mem-005"


class TestConversationSummary:
    def test_construction(self) -> None:
        summary = ConversationSummary(
            id="conv-001",
            started_at=1000.0,
            ended_at=1300.0,
            summary="User asked about the weather",
            turn_count=3,
            topics=["weather", "temperature"],
        )
        assert summary.turn_count == 3
        assert len(summary.topics) == 2

    def test_defaults(self) -> None:
        summary = ConversationSummary(
            id="conv-002",
            started_at=1000.0,
            ended_at=1100.0,
            summary="Brief greeting",
        )
        assert summary.turn_count == 0
        assert summary.topics == []


class TestSearchResult:
    def test_search_result(self) -> None:
        entry = MemoryEntry(
            id="mem-001",
            content="User's name is Andrew",
            category=MemoryCategory.FACT,
        )
        result = SearchResult(entry=entry, similarity=0.87)
        assert result.similarity == 0.87
        assert result.entry.content == "User's name is Andrew"

    def test_similarity_range(self) -> None:
        entry = MemoryEntry(id="mem-001", content="test", category=MemoryCategory.FACT)
        low = SearchResult(entry=entry, similarity=0.3)
        high = SearchResult(entry=entry, similarity=0.99)
        assert low.similarity < high.similarity
