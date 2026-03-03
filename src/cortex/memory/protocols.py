"""Memory system protocol interfaces."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from cortex.memory.types import ConversationSummary, MemoryCategory, MemoryEntry, SearchResult


@runtime_checkable
class MemoryStore(Protocol):
    """Persistent memory storage (short-term + long-term)."""

    async def save_conversation(self, summary: ConversationSummary) -> None:
        """Save a completed conversation summary (short-term)."""
        ...

    async def get_recent_conversations(self, limit: int = 10) -> list[ConversationSummary]:
        """Retrieve recent conversation summaries."""
        ...

    async def save_fact(self, entry: MemoryEntry) -> None:
        """Save an atomic fact to long-term memory."""
        ...

    async def search(
        self,
        embedding: NDArray[np.float32],
        top_k: int = 3,
        threshold: float = 0.3,
    ) -> list[SearchResult]:
        """Search long-term memory by embedding similarity."""
        ...

    async def get_all_facts(self, category: MemoryCategory | None = None) -> list[MemoryEntry]:
        """Retrieve all facts, optionally filtered by category."""
        ...


@runtime_checkable
class EmbeddingService(Protocol):
    """Text embedding for memory retrieval."""

    async def embed(self, text: str) -> NDArray[np.float32]:
        """Embed text into a vector (384-dim for all-MiniLM-L6-v2)."""
        ...

    @property
    def dimensions(self) -> int:
        """Embedding vector dimensionality."""
        ...
