"""Memory tools — query and save facts. Tier 0 (safe).

Wired to MemoryStore + EmbeddingService backends. Falls back to
stub responses if no backend is configured.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from cortex.agent.types import ToolResult
from cortex.memory.types import MemoryCategory, MemoryEntry

logger = logging.getLogger(__name__)

# Module-level backends — set via set_memory_backend()
_store: Any = None
_embedder: Any = None


def set_memory_backend(store: Any, embedder: Any) -> None:
    """Wire the memory tools to a real backend."""
    global _store, _embedder  # noqa: PLW0603
    _store = store
    _embedder = embedder


def get_memory_backend() -> tuple[Any, Any]:
    """Get the current memory backend (for testing)."""
    return _store, _embedder


class MemoryQueryTool:
    """Search long-term memory for relevant facts."""

    @property
    def name(self) -> str:
        return "memory_query"

    @property
    def description(self) -> str:
        return "Search memory for facts"

    @property
    def permission_tier(self) -> int:
        return 0

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "memory_query",
            "description": "Search memory for facts",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for",
                    },
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        query = arguments.get("query", "")
        if not query:
            return ToolResult(
                tool_name="memory_query",
                success=False,
                error="Query required",
            )

        if _store is None or _embedder is None:
            return ToolResult(
                tool_name="memory_query",
                success=True,
                data=[],
                display_text="I don't have any relevant memories yet.",
            )

        try:
            embedding = await _embedder.embed(query)
            results = await _store.search(embedding, top_k=3, threshold=0.3)
            if not results:
                return ToolResult(
                    tool_name="memory_query",
                    success=True,
                    data=[],
                    display_text="I don't have any relevant memories about that.",
                )

            facts = [r.entry.content for r in results]
            display = "Here's what I remember: " + ". ".join(facts) + "."
            return ToolResult(
                tool_name="memory_query",
                success=True,
                data=facts,
                display_text=display,
            )
        except Exception as e:
            logger.exception("Memory query failed")
            return ToolResult(
                tool_name="memory_query",
                success=False,
                error=str(e),
            )


class MemorySaveTool:
    """Save a fact to long-term memory."""

    @property
    def name(self) -> str:
        return "memory_save"

    @property
    def description(self) -> str:
        return "Save a fact to memory"

    @property
    def permission_tier(self) -> int:
        return 0

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": "memory_save",
            "description": "Save a fact to memory",
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "Fact to remember",
                    },
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        fact = arguments.get("fact", "")
        if not fact:
            return ToolResult(
                tool_name="memory_save",
                success=False,
                error="Fact required",
            )

        if _store is None or _embedder is None:
            return ToolResult(
                tool_name="memory_save",
                success=True,
                data={"fact": fact},
                display_text=f"I'll remember that: {fact}",
            )

        try:
            embedding = await _embedder.embed(fact)

            # Check for duplicates
            dupes = await _store.search(embedding, top_k=1, threshold=0.85)
            if dupes:
                return ToolResult(
                    tool_name="memory_save",
                    success=True,
                    data={"fact": fact, "duplicate": True},
                    display_text="I already know that.",
                )

            entry = MemoryEntry(
                id=uuid.uuid4().hex[:16],
                content=fact,
                category=MemoryCategory.FACT,
                embedding=embedding,
                confidence=0.95,
                created_at=time.time(),
            )
            await _store.save_fact(entry)
            return ToolResult(
                tool_name="memory_save",
                success=True,
                data={"fact": fact, "id": entry.id},
                display_text=f"I'll remember that: {fact}",
            )
        except Exception as e:
            logger.exception("Memory save failed")
            return ToolResult(
                tool_name="memory_save",
                success=False,
                error=str(e),
            )
