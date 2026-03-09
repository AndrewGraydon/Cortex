"""Knowledge retriever — embeds queries and formats results for context injection.

Returns a single high-relevance passage (~200 tokens) for injection into
the 2,047-token context budget.
"""

from __future__ import annotations

import logging
from typing import Any

from cortex.knowledge.types import KnowledgeSearchResult

logger = logging.getLogger(__name__)


class KnowledgeRetriever:
    """Retrieves knowledge passages and formats for context assembly."""

    def __init__(
        self,
        store: Any,  # KnowledgeStore
        embedder: Any,  # EmbeddingService
        top_k: int = 1,
        threshold: float = 0.3,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._top_k = top_k
        self._threshold = threshold

    async def search(self, query: str) -> list[KnowledgeSearchResult]:
        """Search the knowledge store for relevant passages."""
        if not query.strip():
            return []
        embedding = await self._embedder.embed(query)
        results: list[KnowledgeSearchResult] = await self._store.search(
            embedding, top_k=self._top_k, threshold=self._threshold
        )
        logger.debug(
            "Knowledge search for '%s': %d results (top sim=%.3f)",
            query[:50],
            len(results),
            results[0].similarity if results else 0.0,
        )
        return results

    async def format_knowledge_block(self, query: str) -> str:
        """Retrieve and format knowledge as a text block for context injection.

        Returns empty string if no relevant passages found.
        Format:
            [Knowledge]
            Source: Document Title
            <passage text>
        """
        results = await self.search(query)
        if not results:
            return ""

        best = results[0]
        lines = [
            "[Knowledge]",
            f"Source: {best.document_title}",
            best.chunk.content,
        ]
        return "\n".join(lines)
