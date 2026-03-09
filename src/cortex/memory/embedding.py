"""Embedding service — text vectorization for memory retrieval.

Provides a MockEmbeddingService for dev/testing that returns
deterministic hash-seeded 384-dim vectors. The real ONNX-based
service loads all-MiniLM-L6-v2 on the Pi's CPU.
"""

from __future__ import annotations

import hashlib

import numpy as np
from numpy.typing import NDArray

from cortex.memory.embedding_protocol import EmbeddingService

__all__ = ["EMBEDDING_DIM", "EmbeddingService", "MockEmbeddingService"]

EMBEDDING_DIM = 384


class MockEmbeddingService:
    """Deterministic mock embedding — same text always yields same vector.

    Uses SHA-256 hash as seed for a numpy random generator to produce
    consistent 384-dim float32 vectors. Good enough for dev testing:
    similar strings won't have similar vectors, but dedup/retrieval
    logic can still be exercised.
    """

    @property
    def dimensions(self) -> int:
        return EMBEDDING_DIM

    async def embed(self, text: str) -> NDArray[np.float32]:
        """Embed text into a deterministic 384-dim vector."""
        seed = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
        # Normalize to unit length (cosine similarity requires this)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    async def embed_batch(self, texts: list[str]) -> list[NDArray[np.float32]]:
        """Embed multiple texts."""
        return [await self.embed(t) for t in texts]
