"""Tests for SQLite memory store — conversations + facts + search."""

from __future__ import annotations

import time

import numpy as np
import pytest

from cortex.memory.embedding import MockEmbeddingService
from cortex.memory.store import SqliteMemoryStore
from cortex.memory.types import ConversationSummary, MemoryCategory, MemoryEntry


@pytest.fixture
async def store(tmp_path) -> SqliteMemoryStore:
    db_path = str(tmp_path / "test_memory.db")
    s = SqliteMemoryStore(db_path=db_path)
    await s.start()
    yield s
    await s.stop()


@pytest.fixture
def embedder() -> MockEmbeddingService:
    return MockEmbeddingService()


def make_entry(
    content: str,
    category: MemoryCategory = MemoryCategory.FACT,
    embedding: np.ndarray | None = None,
    entry_id: str | None = None,
) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id or f"mem-{hash(content) % 10000:04d}",
        content=content,
        category=category,
        embedding=embedding,
        created_at=time.time(),
    )


class TestStoreLifecycle:
    async def test_start_creates_tables(self, store: SqliteMemoryStore) -> None:
        count = await store.fact_count()
        assert count == 0

    async def test_stop_and_restart(self, tmp_path) -> None:
        db_path = str(tmp_path / "restart.db")
        s = SqliteMemoryStore(db_path=db_path)
        await s.start()
        await s.stop()
        # Restart should work
        s2 = SqliteMemoryStore(db_path=db_path)
        await s2.start()
        count = await s2.fact_count()
        assert count == 0
        await s2.stop()

    async def test_operations_before_start_raise(self, tmp_path) -> None:
        s = SqliteMemoryStore(db_path=str(tmp_path / "nope.db"))
        with pytest.raises(RuntimeError, match="not started"):
            await s.fact_count()


class TestConversations:
    async def test_save_conversation(self, store: SqliteMemoryStore) -> None:
        summary = ConversationSummary(
            id="conv-001",
            started_at=1000.0,
            ended_at=1060.0,
            summary="Discussed the weather.",
            turn_count=3,
            topics=["weather"],
        )
        await store.save_conversation(summary)
        count = await store.conversation_count()
        assert count == 1

    async def test_get_recent_conversations(self, store: SqliteMemoryStore) -> None:
        for i in range(5):
            await store.save_conversation(
                ConversationSummary(
                    id=f"conv-{i:03d}",
                    started_at=float(i * 100),
                    ended_at=float(i * 100 + 60),
                    summary=f"Conversation {i}",
                    turn_count=i + 1,
                )
            )
        results = await store.get_recent_conversations(limit=3)
        assert len(results) == 3
        # Newest first
        assert results[0].ended_at > results[-1].ended_at

    async def test_conversation_topics_round_trip(self, store: SqliteMemoryStore) -> None:
        summary = ConversationSummary(
            id="conv-topics",
            started_at=100.0,
            ended_at=200.0,
            summary="Test topics",
            topics=["math", "science", "cooking"],
        )
        await store.save_conversation(summary)
        results = await store.get_recent_conversations()
        assert results[0].topics == ["math", "science", "cooking"]


class TestFacts:
    async def test_save_fact(self, store: SqliteMemoryStore) -> None:
        entry = make_entry("User's name is Andrew")
        await store.save_fact(entry)
        count = await store.fact_count()
        assert count == 1

    async def test_save_fact_with_embedding(
        self, store: SqliteMemoryStore, embedder: MockEmbeddingService
    ) -> None:
        embedding = await embedder.embed("User's name is Andrew")
        entry = make_entry("User's name is Andrew", embedding=embedding)
        await store.save_fact(entry)
        facts = await store.get_all_facts()
        assert len(facts) == 1
        assert facts[0].embedding is not None
        assert facts[0].embedding.shape == (384,)

    async def test_get_all_facts(self, store: SqliteMemoryStore) -> None:
        for i in range(3):
            await store.save_fact(make_entry(f"Fact {i}", entry_id=f"f-{i}"))
        facts = await store.get_all_facts()
        assert len(facts) == 3

    async def test_get_facts_by_category(self, store: SqliteMemoryStore) -> None:
        await store.save_fact(make_entry("Likes coffee", MemoryCategory.PREFERENCE, entry_id="p1"))
        await store.save_fact(make_entry("Name is Andrew", MemoryCategory.PERSON, entry_id="n1"))
        await store.save_fact(make_entry("Prefers 22C", MemoryCategory.PREFERENCE, entry_id="p2"))

        prefs = await store.get_all_facts(category=MemoryCategory.PREFERENCE)
        assert len(prefs) == 2
        people = await store.get_all_facts(category=MemoryCategory.PERSON)
        assert len(people) == 1

    async def test_superseded_facts_hidden(self, store: SqliteMemoryStore) -> None:
        old = make_entry("Name is Bob", entry_id="old-1")
        old.superseded_by = "new-1"
        await store.save_fact(old)
        await store.save_fact(make_entry("Name is Andrew", entry_id="new-1"))
        facts = await store.get_all_facts()
        assert len(facts) == 1
        assert facts[0].content == "Name is Andrew"


class TestSearch:
    async def test_search_by_embedding(
        self,
        store: SqliteMemoryStore,
        embedder: MockEmbeddingService,
    ) -> None:
        # Save some facts with embeddings
        for i, fact in enumerate(
            ["User's name is Andrew", "User likes coffee", "User lives in Vancouver"]
        ):
            embedding = await embedder.embed(fact)
            await store.save_fact(make_entry(fact, embedding=embedding, entry_id=f"s-{i}"))

        # Search with the same text should find it
        query_emb = await embedder.embed("User's name is Andrew")
        results = await store.search(query_emb, top_k=3, threshold=0.0)
        assert len(results) >= 1
        # The exact match should have highest similarity
        assert results[0].entry.content == "User's name is Andrew"
        assert results[0].similarity > 0.99  # Same hash = same vector

    async def test_search_empty_store(
        self, store: SqliteMemoryStore, embedder: MockEmbeddingService
    ) -> None:
        query_emb = await embedder.embed("anything")
        results = await store.search(query_emb)
        assert results == []

    async def test_search_respects_threshold(
        self,
        store: SqliteMemoryStore,
        embedder: MockEmbeddingService,
    ) -> None:
        embedding = await embedder.embed("coffee")
        await store.save_fact(make_entry("User likes coffee", embedding=embedding, entry_id="t1"))

        # Different query should have low similarity (hash-based mock)
        query_emb = await embedder.embed("something completely different")
        results = await store.search(query_emb, threshold=0.99)
        # Mock embeddings are hash-based, so different text = different direction
        assert len(results) == 0

    async def test_search_top_k(
        self,
        store: SqliteMemoryStore,
        embedder: MockEmbeddingService,
    ) -> None:
        for i in range(10):
            emb = await embedder.embed(f"fact {i}")
            await store.save_fact(make_entry(f"Fact number {i}", embedding=emb, entry_id=f"tk-{i}"))
        # Use one of the stored embeddings as query
        query_emb = await embedder.embed("fact 5")
        results = await store.search(query_emb, top_k=2, threshold=0.0)
        assert len(results) == 2

    async def test_find_duplicates(
        self,
        store: SqliteMemoryStore,
        embedder: MockEmbeddingService,
    ) -> None:
        emb = await embedder.embed("User's name is Andrew")
        await store.save_fact(make_entry("User's name is Andrew", embedding=emb, entry_id="dup1"))
        # Same embedding should be a duplicate
        dupes = await store.find_duplicates(emb, threshold=0.85)
        assert len(dupes) >= 1

    async def test_search_updates_last_referenced(
        self,
        store: SqliteMemoryStore,
        embedder: MockEmbeddingService,
    ) -> None:
        emb = await embedder.embed("test fact")
        entry = make_entry("Test fact for referencing", embedding=emb, entry_id="ref1")
        entry.last_referenced = 0.0
        await store.save_fact(entry)

        # Search should update last_referenced
        await store.search(emb, top_k=1, threshold=0.0)
        facts = await store.get_all_facts()
        assert facts[0].last_referenced > 0.0
