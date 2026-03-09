"""Memory retrieval — searches memory and formats results for context injection.

The retriever embeds the query, searches the memory store, and formats
matching facts as a memory block for P4 injection into the system prompt.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from numpy.typing import NDArray

from cortex.memory.embedding_protocol import EmbeddingService
from cortex.memory.types import SearchResult

logger = logging.getLogger(__name__)


class MemoryRetriever:
    """Retrieves relevant memories and formats them for context assembly.

    Args:
        store: MemoryStore backend (SqliteMemoryStore or mock).
        embedder: EmbeddingService for vectorizing queries.
        top_k: Maximum number of memories to retrieve.
        threshold: Minimum cosine similarity for inclusion.
    """

    def __init__(
        self,
        store: Any,  # MemoryStore protocol
        embedder: EmbeddingService,
        top_k: int = 3,
        threshold: float = 0.3,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._top_k = top_k
        self._threshold = threshold

    async def retrieve(self, query: str) -> list[SearchResult]:
        """Search memory for facts relevant to the query.

        Returns up to `top_k` results above the similarity threshold.
        """
        if not query.strip():
            return []

        embedding: NDArray[np.float32] = await self._embedder.embed(query)
        results: list[SearchResult] = await self._store.search(
            embedding, top_k=self._top_k, threshold=self._threshold
        )
        logger.debug(
            "Memory retrieval for '%s': %d results (top sim=%.3f)",
            query[:50],
            len(results),
            results[0].similarity if results else 0.0,
        )
        return results

    async def format_memory_block(self, query: str) -> str:
        """Retrieve memories and format as a text block for P4 injection.

        Returns empty string if no relevant memories found.
        Format:
            [Memory]
            - User's name is Andrew
            - User prefers 22°C
            - User lives in Vancouver
        """
        results = await self.retrieve(query)
        if not results:
            return ""

        lines = ["[Memory]"]
        for r in results:
            lines.append(f"- {r.entry.content}")
        return "\n".join(lines)

    async def check_duplicate(
        self,
        embedding: NDArray[np.float32],
        threshold: float = 0.85,
    ) -> bool:
        """Check if a near-duplicate already exists in memory."""
        results = await self._store.search(embedding, top_k=1, threshold=threshold)
        return len(results) > 0
