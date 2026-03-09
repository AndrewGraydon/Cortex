"""Tests for semantic memory — save facts with embeddings, retrieve by semantic search.

Uses MockEmbeddingService to verify the embedding pipeline works end-to-end:
save facts with embeddings, then search and verify similar/dissimilar results.
"""

from __future__ import annotations

import time

import pytest

from cortex.memory.embedding import MockEmbeddingService
from cortex.memory.retrieval import MemoryRetriever
from cortex.memory.store import SqliteMemoryStore
from cortex.memory.types import MemoryCategory, MemoryEntry


@pytest.fixture
async def store(tmp_path: object) -> SqliteMemoryStore:
    db_path = str(tmp_path) + "/semantic.db"  # type: ignore[operator]
    s = SqliteMemoryStore(db_path=db_path)
    await s.start()
    yield s  # type: ignore[misc]
    await s.stop()


@pytest.fixture
def embedder() -> MockEmbeddingService:
    return MockEmbeddingService()


@pytest.fixture
def retriever(store: SqliteMemoryStore, embedder: MockEmbeddingService) -> MemoryRetriever:
    return MemoryRetriever(store=store, embedder=embedder, top_k=3, threshold=0.0)


async def _save_fact(
    store: SqliteMemoryStore,
    embedder: MockEmbeddingService,
    content: str,
    category: MemoryCategory = MemoryCategory.FACT,
) -> MemoryEntry:
    """Helper to save a fact with its embedding."""
    embedding = await embedder.embed(content)
    entry = MemoryEntry(
        id=f"mem-{hash(content) % 10000:04d}",
        content=content,
        category=category,
        embedding=embedding,
        created_at=time.time(),
    )
    await store.save_fact(entry)
    return entry


class TestSaveAndRetrieve:
    async def test_save_fact_with_embedding(
        self, store: SqliteMemoryStore, embedder: MockEmbeddingService
    ) -> None:
        entry = await _save_fact(store, embedder, "User's name is Andrew")
        assert entry.embedding is not None
        assert entry.embedding.shape == (384,)

    async def test_retrieve_by_exact_query(
        self,
        store: SqliteMemoryStore,
        embedder: MockEmbeddingService,
        retriever: MemoryRetriever,
    ) -> None:
        await _save_fact(store, embedder, "User's name is Andrew")
        # Same text → same embedding → similarity = 1.0
        results = await retriever.retrieve("User's name is Andrew")
        assert len(results) >= 1
        assert results[0].entry.content == "User's name is Andrew"
        assert results[0].similarity > 0.99

    async def test_retrieve_empty_query(self, retriever: MemoryRetriever) -> None:
        results = await retriever.retrieve("")
        assert results == []

    async def test_format_memory_block(
        self,
        store: SqliteMemoryStore,
        embedder: MockEmbeddingService,
        retriever: MemoryRetriever,
    ) -> None:
        await _save_fact(store, embedder, "User lives in Vancouver")
        block = await retriever.format_memory_block("User lives in Vancouver")
        assert "[Memory]" in block
        assert "User lives in Vancouver" in block

    async def test_format_empty_returns_empty(self, retriever: MemoryRetriever) -> None:
        block = await retriever.format_memory_block("any query")
        assert block == ""


class TestSimilarity:
    async def test_same_text_high_similarity(
        self,
        store: SqliteMemoryStore,
        embedder: MockEmbeddingService,
        retriever: MemoryRetriever,
    ) -> None:
        await _save_fact(store, embedder, "User prefers 22 degrees")
        results = await retriever.retrieve("User prefers 22 degrees")
        assert len(results) >= 1
        assert results[0].similarity > 0.99

    async def test_multiple_facts_ranked(
        self,
        store: SqliteMemoryStore,
        embedder: MockEmbeddingService,
        retriever: MemoryRetriever,
    ) -> None:
        await _save_fact(store, embedder, "User's name is Andrew")
        await _save_fact(store, embedder, "User lives in Vancouver")
        await _save_fact(store, embedder, "User prefers metric units")

        # Query matching first fact exactly
        results = await retriever.retrieve("User's name is Andrew")
        assert len(results) >= 1
        # Best result should be the exact match
        assert results[0].entry.content == "User's name is Andrew"

    async def test_dedup_detection(
        self,
        store: SqliteMemoryStore,
        embedder: MockEmbeddingService,
        retriever: MemoryRetriever,
    ) -> None:
        embedding = await embedder.embed("User's name is Andrew")
        is_dup = await retriever.check_duplicate(embedding, threshold=0.85)
        assert is_dup is False  # No entries yet

        await _save_fact(store, embedder, "User's name is Andrew")
        is_dup = await retriever.check_duplicate(embedding, threshold=0.85)
        assert is_dup is True  # Should find the duplicate


class TestCategories:
    async def test_fact_category(
        self, store: SqliteMemoryStore, embedder: MockEmbeddingService
    ) -> None:
        await _save_fact(store, embedder, "Pi runs Debian 12", MemoryCategory.FACT)
        facts = await store.get_all_facts(MemoryCategory.FACT)
        assert len(facts) == 1
        assert facts[0].content == "Pi runs Debian 12"

    async def test_preference_category(
        self, store: SqliteMemoryStore, embedder: MockEmbeddingService
    ) -> None:
        await _save_fact(store, embedder, "User prefers dark mode", MemoryCategory.PREFERENCE)
        prefs = await store.get_all_facts(MemoryCategory.PREFERENCE)
        assert len(prefs) == 1

    async def test_mixed_categories(
        self, store: SqliteMemoryStore, embedder: MockEmbeddingService
    ) -> None:
        await _save_fact(store, embedder, "Fact one", MemoryCategory.FACT)
        await _save_fact(store, embedder, "Pref one", MemoryCategory.PREFERENCE)
        await _save_fact(store, embedder, "Person one", MemoryCategory.PERSON)

        all_facts = await store.get_all_facts()
        assert len(all_facts) == 3
        facts_only = await store.get_all_facts(MemoryCategory.FACT)
        assert len(facts_only) == 1
