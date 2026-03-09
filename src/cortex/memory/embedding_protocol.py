"""Embedding service protocol — interface for text vectorization.

Both MockEmbeddingService and OnnxEmbeddingService satisfy this protocol.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray


@runtime_checkable
class EmbeddingService(Protocol):
    """Protocol for text embedding services.

    Implementations must provide:
    - dimensions: the dimensionality of produced vectors
    - embed(text): vectorize a single text
    - embed_batch(texts): vectorize multiple texts
    """

    @property
    def dimensions(self) -> int: ...

    async def embed(self, text: str) -> NDArray[np.float32]: ...

    async def embed_batch(self, texts: list[str]) -> list[NDArray[np.float32]]: ...
