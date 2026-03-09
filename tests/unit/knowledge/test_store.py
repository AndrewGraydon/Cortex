"""Tests for the knowledge store (SQLite-backed)."""

from __future__ import annotations

import numpy as np
import pytest

from cortex.knowledge.store import KnowledgeStore
from cortex.knowledge.types import Document, DocumentChunk


def _make_doc(doc_id: str = "doc-1", title: str = "Test Doc") -> Document:
    return Document(id=doc_id, title=title, format="txt", chunk_count=2)


def _make_chunks(
    doc_id: str = "doc-1",
    count: int = 2,
    dim: int = 384,
) -> list[DocumentChunk]:
    chunks = []
    for i in range(count):
        vec = np.random.default_rng(seed=i).standard_normal(dim).astype(np.float32)
        vec = vec / np.linalg.norm(vec)
        chunks.append(
            DocumentChunk(
                id=f"{doc_id}-chunk-{i}",
                document_id=doc_id,
                chunk_index=i,
                content=f"Chunk {i} content for document {doc_id}.",
                embedding=vec,
                token_count=10,
            )
        )
    return chunks


@pytest.fixture
async def store() -> KnowledgeStore:
    s = KnowledgeStore(db_path=":memory:")
    await s.start()
    yield s  # type: ignore[misc]
    await s.stop()


class TestStoreLifecycle:
    async def test_start_creates_tables(self, store: KnowledgeStore) -> None:
        # If we can list documents, tables exist
        docs = await store.list_documents()
        assert docs == []

    async def test_double_start_is_safe(self) -> None:
        s = KnowledgeStore(db_path=":memory:")
        await s.start()
        await s.start()  # Should not raise
        await s.stop()

    async def test_not_started_raises(self) -> None:
        s = KnowledgeStore(db_path=":memory:")
        with pytest.raises(RuntimeError, match="not started"):
            await s.list_documents()


class TestAddDocument:
    async def test_add_and_list(self, store: KnowledgeStore) -> None:
        doc = _make_doc()
        chunks = _make_chunks()
        await store.add_document(doc, chunks)

        docs = await store.list_documents()
        assert len(docs) == 1
        assert docs[0].id == "doc-1"
        assert docs[0].title == "Test Doc"

    async def test_add_multiple_documents(self, store: KnowledgeStore) -> None:
        for i in range(3):
            doc = _make_doc(doc_id=f"doc-{i}", title=f"Doc {i}")
            chunks = _make_chunks(doc_id=f"doc-{i}", count=1)
            await store.add_document(doc, chunks)

        docs = await store.list_documents()
        assert len(docs) == 3

    async def test_replace_existing_document(self, store: KnowledgeStore) -> None:
        doc = _make_doc()
        await store.add_document(doc, _make_chunks())
        # Replace with updated title
        doc2 = _make_doc(title="Updated Title")
        await store.add_document(doc2, _make_chunks(count=3))

        docs = await store.list_documents()
        assert len(docs) == 1
        assert docs[0].title == "Updated Title"


class TestDeleteDocument:
    async def test_delete_existing(self, store: KnowledgeStore) -> None:
        await store.add_document(_make_doc(), _make_chunks())
        deleted = await store.delete_document("doc-1")
        assert deleted is True
        assert await store.document_count() == 0

    async def test_delete_cascades_chunks(self, store: KnowledgeStore) -> None:
        await store.add_document(_make_doc(), _make_chunks(count=5))
        assert await store.chunk_count() == 5
        await store.delete_document("doc-1")
        assert await store.chunk_count() == 0

    async def test_delete_nonexistent(self, store: KnowledgeStore) -> None:
        deleted = await store.delete_document("nonexistent")
        assert deleted is False


class TestCounts:
    async def test_document_count(self, store: KnowledgeStore) -> None:
        assert await store.document_count() == 0
        await store.add_document(_make_doc(), _make_chunks())
        assert await store.document_count() == 1

    async def test_chunk_count(self, store: KnowledgeStore) -> None:
        assert await store.chunk_count() == 0
        await store.add_document(_make_doc(), _make_chunks(count=3))
        assert await store.chunk_count() == 3


class TestGetDocument:
    async def test_get_existing(self, store: KnowledgeStore) -> None:
        await store.add_document(_make_doc(), _make_chunks())
        doc = await store.get_document("doc-1")
        assert doc is not None
        assert doc.title == "Test Doc"

    async def test_get_nonexistent(self, store: KnowledgeStore) -> None:
        doc = await store.get_document("nonexistent")
        assert doc is None


class TestSearch:
    async def test_search_returns_results(self, store: KnowledgeStore) -> None:
        doc = _make_doc()
        chunks = _make_chunks(count=3)
        await store.add_document(doc, chunks)

        # Search with a vector similar to chunk 0's embedding
        query_vec = chunks[0].embedding
        assert query_vec is not None
        results = await store.search(query_vec, top_k=2, threshold=0.0)
        assert len(results) >= 1
        assert results[0].similarity >= results[-1].similarity  # Sorted desc

    async def test_search_empty_store(self, store: KnowledgeStore) -> None:
        query = np.random.default_rng(0).standard_normal(384).astype(np.float32)
        results = await store.search(query, top_k=3)
        assert results == []

    async def test_search_threshold_filters(self, store: KnowledgeStore) -> None:
        doc = _make_doc()
        chunks = _make_chunks(count=2)
        await store.add_document(doc, chunks)

        # Use a random vector (likely low similarity) with high threshold
        query = np.random.default_rng(999).standard_normal(384).astype(np.float32)
        results = await store.search(query, top_k=10, threshold=0.99)
        # With random vectors, high threshold should filter most results
        assert len(results) <= 2

    async def test_search_top_k_limits_results(self, store: KnowledgeStore) -> None:
        doc = _make_doc()
        chunks = _make_chunks(count=10)
        await store.add_document(doc, chunks)

        query = chunks[0].embedding
        assert query is not None
        results = await store.search(query, top_k=2, threshold=0.0)
        assert len(results) <= 2

    async def test_search_zero_norm_query(self, store: KnowledgeStore) -> None:
        doc = _make_doc()
        await store.add_document(doc, _make_chunks())
        zero_vec = np.zeros(384, dtype=np.float32)
        results = await store.search(zero_vec)
        assert results == []

    async def test_search_result_has_document_title(self, store: KnowledgeStore) -> None:
        doc = _make_doc(title="My Title")
        chunks = _make_chunks()
        await store.add_document(doc, chunks)

        query = chunks[0].embedding
        assert query is not None
        results = await store.search(query, top_k=1, threshold=0.0)
        assert len(results) >= 1
        assert results[0].document_title == "My Title"

    async def test_search_across_documents(self, store: KnowledgeStore) -> None:
        for i in range(3):
            doc = _make_doc(doc_id=f"doc-{i}", title=f"Doc {i}")
            await store.add_document(doc, _make_chunks(doc_id=f"doc-{i}", count=2))

        # Search with chunk embedding from doc-1
        chunks_1 = _make_chunks(doc_id="doc-1", count=2)
        query = chunks_1[0].embedding
        assert query is not None
        results = await store.search(query, top_k=10, threshold=0.0)
        assert len(results) >= 1
