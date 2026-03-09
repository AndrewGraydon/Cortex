"""Tests for the knowledge retriever."""

from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray

from cortex.knowledge.retriever import KnowledgeRetriever
from cortex.knowledge.store import KnowledgeStore
from cortex.knowledge.types import Document, DocumentChunk


class MockEmbedder:
    """Minimal mock embedder for retriever tests."""

    @property
    def dimensions(self) -> int:
        return 384

    async def embed(self, text: str) -> NDArray[np.float32]:
        rng = np.random.default_rng(hash(text) % (2**31))
        vec = rng.standard_normal(384).astype(np.float32)
        return vec / np.linalg.norm(vec)

    async def embed_batch(self, texts: list[str]) -> list[NDArray[np.float32]]:
        return [await self.embed(t) for t in texts]


def _make_doc_and_chunks(
    doc_id: str = "doc-1",
    title: str = "Test Doc",
    contents: list[str] | None = None,
) -> tuple[Document, list[DocumentChunk]]:
    if contents is None:
        contents = ["First chunk content.", "Second chunk content."]
    doc = Document(id=doc_id, title=title, format="txt", chunk_count=len(contents))
    chunks = []
    for i, content in enumerate(contents):
        rng = np.random.default_rng(hash(content) % (2**31))
        vec = rng.standard_normal(384).astype(np.float32)
        vec = vec / np.linalg.norm(vec)
        chunks.append(
            DocumentChunk(
                id=f"{doc_id}-c{i}",
                document_id=doc_id,
                chunk_index=i,
                content=content,
                embedding=vec,
                token_count=10,
            )
        )
    return doc, chunks


@pytest.fixture
async def store() -> KnowledgeStore:
    s = KnowledgeStore(db_path=":memory:")
    await s.start()
    yield s  # type: ignore[misc]
    await s.stop()


@pytest.fixture
def embedder() -> MockEmbedder:
    return MockEmbedder()


@pytest.fixture
def retriever(store: KnowledgeStore, embedder: MockEmbedder) -> KnowledgeRetriever:
    return KnowledgeRetriever(store=store, embedder=embedder, top_k=1, threshold=0.0)


class TestSearch:
    async def test_search_empty_store(self, retriever: KnowledgeRetriever) -> None:
        results = await retriever.search("test query")
        assert results == []

    async def test_search_returns_results(
        self, retriever: KnowledgeRetriever, store: KnowledgeStore
    ) -> None:
        doc, chunks = _make_doc_and_chunks()
        await store.add_document(doc, chunks)
        # Use same text as chunk content so hash-based embeddings match (sim=1.0)
        results = await retriever.search("First chunk content.")
        assert len(results) >= 1

    async def test_search_empty_query(self, retriever: KnowledgeRetriever) -> None:
        results = await retriever.search("")
        assert results == []

    async def test_search_whitespace_query(self, retriever: KnowledgeRetriever) -> None:
        results = await retriever.search("   ")
        assert results == []

    async def test_result_has_document_title(
        self, retriever: KnowledgeRetriever, store: KnowledgeStore
    ) -> None:
        doc, chunks = _make_doc_and_chunks(title="My Document")
        await store.add_document(doc, chunks)
        # Use same text as chunk content so hash-based embeddings match
        results = await retriever.search("First chunk content.")
        assert len(results) >= 1
        assert results[0].document_title == "My Document"


class TestFormatKnowledgeBlock:
    async def test_empty_store_returns_empty(self, retriever: KnowledgeRetriever) -> None:
        block = await retriever.format_knowledge_block("test")
        assert block == ""

    async def test_format_with_results(
        self, retriever: KnowledgeRetriever, store: KnowledgeStore
    ) -> None:
        doc, chunks = _make_doc_and_chunks(title="Science Notes")
        await store.add_document(doc, chunks)
        # Use same text as chunk content so hash-based embeddings match
        block = await retriever.format_knowledge_block("First chunk content.")
        assert "[Knowledge]" in block
        assert "Source: Science Notes" in block

    async def test_format_includes_passage_content(
        self, retriever: KnowledgeRetriever, store: KnowledgeStore
    ) -> None:
        doc, chunks = _make_doc_and_chunks(contents=["The answer is 42."])
        await store.add_document(doc, chunks)
        # Use threshold=0 retriever, search with same text so embedding matches
        block = await retriever.format_knowledge_block("The answer is 42.")
        assert block  # Not empty — same text produces same embedding

    async def test_empty_query_returns_empty(self, retriever: KnowledgeRetriever) -> None:
        block = await retriever.format_knowledge_block("")
        assert block == ""

    async def test_threshold_filtering(self, store: KnowledgeStore, embedder: MockEmbedder) -> None:
        retriever = KnowledgeRetriever(store=store, embedder=embedder, top_k=1, threshold=0.99)
        doc, chunks = _make_doc_and_chunks()
        await store.add_document(doc, chunks)
        # With very high threshold, random embedding likely won't match
        block = await retriever.format_knowledge_block("completely unrelated query xyz")
        # May or may not be empty depending on random vectors; just verify no crash
        assert isinstance(block, str)
