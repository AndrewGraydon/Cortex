"""Tests for memory retrieval — search and formatting."""

from __future__ import annotations

import time

import pytest

from cortex.memory.embedding import MockEmbeddingService
from cortex.memory.retrieval import MemoryRetriever
from cortex.memory.store import SqliteMemoryStore
from cortex.memory.types import MemoryCategory, MemoryEntry


@pytest.fixture
async def store(tmp_path) -> SqliteMemoryStore:
    db_path = str(tmp_path / "test_retrieval.db")
    s = SqliteMemoryStore(db_path=db_path)
    await s.start()
    yield s
    await s.stop()


@pytest.fixture
def embedder() -> MockEmbeddingService:
    return MockEmbeddingService()


@pytest.fixture
def retriever(store, embedder) -> MemoryRetriever:
    return MemoryRetriever(store=store, embedder=embedder)


async def populate_facts(
    store: SqliteMemoryStore,
    embedder: MockEmbeddingService,
    facts: list[str],
) -> None:
    """Helper to populate store with embedded facts."""
    for i, fact in enumerate(facts):
        emb = await embedder.embed(fact)
        entry = MemoryEntry(
            id=f"ret-{i}",
            content=fact,
            category=MemoryCategory.FACT,
            embedding=emb,
            created_at=time.time(),
        )
        await store.save_fact(entry)


class TestRetrieve:
    async def test_retrieve_matching_fact(self, store, embedder, retriever) -> None:
        await populate_facts(store, embedder, ["User's name is Andrew"])
        results = await retriever.retrieve("User's name is Andrew")
        assert len(results) == 1
        assert results[0].entry.content == "User's name is Andrew"

    async def test_retrieve_empty_store(self, retriever) -> None:
        results = await retriever.retrieve("anything")
        assert results == []

    async def test_retrieve_empty_query(self, retriever) -> None:
        results = await retriever.retrieve("")
        assert results == []

    async def test_retrieve_respects_top_k(self, store, embedder) -> None:
        retriever = MemoryRetriever(store=store, embedder=embedder, top_k=1)
        await populate_facts(
            store,
            embedder,
            ["Fact A", "Fact B", "Fact C"],
        )
        # Search for exact match
        results = await retriever.retrieve("Fact A")
        assert len(results) <= 1


class TestFormatMemoryBlock:
    async def test_format_with_results(self, store, embedder, retriever) -> None:
        await populate_facts(store, embedder, ["User's name is Andrew"])
        block = await retriever.format_memory_block("User's name is Andrew")
        assert "[Memory]" in block
        assert "User's name is Andrew" in block

    async def test_format_empty(self, retriever) -> None:
        block = await retriever.format_memory_block("no facts here")
        assert block == ""

    async def test_format_multiple_results(self, store, embedder) -> None:
        retriever = MemoryRetriever(store=store, embedder=embedder, threshold=0.0)
        await populate_facts(
            store,
            embedder,
            ["User's name is Andrew", "User likes coffee", "User lives in Vancouver"],
        )
        block = await retriever.format_memory_block("User's name is Andrew")
        assert "[Memory]" in block
        lines = [line for line in block.split("\n") if line.startswith("- ")]
        assert len(lines) >= 1


class TestDuplicateCheck:
    async def test_detects_duplicate(self, store, embedder, retriever) -> None:
        emb = await embedder.embed("User's name is Andrew")
        entry = MemoryEntry(
            id="dc-1",
            content="User's name is Andrew",
            category=MemoryCategory.FACT,
            embedding=emb,
            created_at=time.time(),
        )
        await store.save_fact(entry)

        is_dup = await retriever.check_duplicate(emb, threshold=0.85)
        assert is_dup

    async def test_not_duplicate(self, store, embedder, retriever) -> None:
        emb_stored = await embedder.embed("User likes coffee")
        entry = MemoryEntry(
            id="dc-2",
            content="User likes coffee",
            category=MemoryCategory.FACT,
            embedding=emb_stored,
            created_at=time.time(),
        )
        await store.save_fact(entry)

        emb_query = await embedder.embed("completely different fact")
        is_dup = await retriever.check_duplicate(emb_query, threshold=0.85)
        assert not is_dup
