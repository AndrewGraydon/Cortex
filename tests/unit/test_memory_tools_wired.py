"""Tests for memory tools with real backend wired in."""

from __future__ import annotations

import time

import pytest

from cortex.agent.tools.builtin.memory_tool import (
    MemoryQueryTool,
    MemorySaveTool,
    set_memory_backend,
)
from cortex.memory.embedding import MockEmbeddingService
from cortex.memory.store import SqliteMemoryStore
from cortex.memory.types import MemoryCategory, MemoryEntry


@pytest.fixture
async def store(tmp_path) -> SqliteMemoryStore:
    db_path = str(tmp_path / "test_tools_memory.db")
    s = SqliteMemoryStore(db_path=db_path)
    await s.start()
    yield s
    await s.stop()


@pytest.fixture
def embedder() -> MockEmbeddingService:
    return MockEmbeddingService()


@pytest.fixture(autouse=True)
def wire_backend(store, embedder):
    set_memory_backend(store, embedder)
    yield
    set_memory_backend(None, None)


class TestMemorySaveToolWired:
    async def test_save_persists(self, store) -> None:
        tool = MemorySaveTool()
        result = await tool.execute({"fact": "User likes tea"})
        assert result.success
        assert "remember" in result.display_text.lower()
        # Check it was persisted
        count = await store.fact_count()
        assert count == 1

    async def test_save_detects_duplicate(self, store, embedder) -> None:
        # Pre-populate with same fact
        emb = await embedder.embed("User likes tea")
        entry = MemoryEntry(
            id="pre-1",
            content="User likes tea",
            category=MemoryCategory.FACT,
            embedding=emb,
            created_at=time.time(),
        )
        await store.save_fact(entry)

        tool = MemorySaveTool()
        result = await tool.execute({"fact": "User likes tea"})
        assert result.success
        assert result.data.get("duplicate") is True
        assert "already" in result.display_text.lower()

    async def test_save_no_fact(self) -> None:
        tool = MemorySaveTool()
        result = await tool.execute({"fact": ""})
        assert not result.success


class TestMemoryQueryToolWired:
    async def test_query_finds_stored_fact(self, store, embedder) -> None:
        # Store a fact
        emb = await embedder.embed("User's name is Andrew")
        entry = MemoryEntry(
            id="q-1",
            content="User's name is Andrew",
            category=MemoryCategory.FACT,
            embedding=emb,
            created_at=time.time(),
        )
        await store.save_fact(entry)

        tool = MemoryQueryTool()
        result = await tool.execute({"query": "User's name is Andrew"})
        assert result.success
        assert "Andrew" in result.display_text

    async def test_query_no_results(self) -> None:
        tool = MemoryQueryTool()
        result = await tool.execute({"query": "something not stored"})
        assert result.success
        assert "don't have" in result.display_text.lower()

    async def test_query_empty(self) -> None:
        tool = MemoryQueryTool()
        result = await tool.execute({"query": ""})
        assert not result.success


class TestMemoryToolsNoBackend:
    @pytest.fixture(autouse=True)
    def clear_backend(self):
        set_memory_backend(None, None)
        yield
        set_memory_backend(None, None)

    async def test_save_without_backend(self) -> None:
        tool = MemorySaveTool()
        result = await tool.execute({"fact": "test fact"})
        assert result.success
        assert "remember" in result.display_text.lower()

    async def test_query_without_backend(self) -> None:
        tool = MemoryQueryTool()
        result = await tool.execute({"query": "test"})
        assert result.success
        assert "don't have" in result.display_text.lower()
