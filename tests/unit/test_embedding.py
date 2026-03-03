"""Tests for embedding service — mock deterministic embeddings."""

from __future__ import annotations

import numpy as np

from cortex.memory.embedding import EMBEDDING_DIM, MockEmbeddingService


class TestMockEmbeddingService:
    async def test_dimensions(self) -> None:
        svc = MockEmbeddingService()
        assert svc.dimensions == EMBEDDING_DIM

    async def test_embed_returns_correct_shape(self) -> None:
        svc = MockEmbeddingService()
        vec = await svc.embed("hello world")
        assert vec.shape == (EMBEDDING_DIM,)
        assert vec.dtype == np.float32

    async def test_embed_is_normalized(self) -> None:
        svc = MockEmbeddingService()
        vec = await svc.embed("test normalization")
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 1e-5

    async def test_embed_deterministic(self) -> None:
        svc = MockEmbeddingService()
        v1 = await svc.embed("same text")
        v2 = await svc.embed("same text")
        np.testing.assert_array_equal(v1, v2)

    async def test_embed_different_text_different_vector(self) -> None:
        svc = MockEmbeddingService()
        v1 = await svc.embed("hello")
        v2 = await svc.embed("goodbye")
        # Different texts should produce different vectors
        assert not np.allclose(v1, v2)

    async def test_embed_batch(self) -> None:
        svc = MockEmbeddingService()
        texts = ["apple", "banana", "cherry"]
        vecs = await svc.embed_batch(texts)
        assert len(vecs) == 3
        for v in vecs:
            assert v.shape == (EMBEDDING_DIM,)

    async def test_embed_empty_string(self) -> None:
        svc = MockEmbeddingService()
        vec = await svc.embed("")
        assert vec.shape == (EMBEDDING_DIM,)

    async def test_cosine_similarity_same_text(self) -> None:
        svc = MockEmbeddingService()
        v1 = await svc.embed("identical")
        v2 = await svc.embed("identical")
        sim = float(np.dot(v1, v2))
        assert abs(sim - 1.0) < 1e-5
