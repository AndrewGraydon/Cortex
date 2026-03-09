"""Knowledge search tool — semantic search over the knowledge store.

Tier 0 (safe, read-only): queries ingested documents and returns
the most relevant passage for the user's query.
"""

from __future__ import annotations

from typing import Any

from cortex.agent.types import ToolResult

_retriever: Any = None


def set_knowledge_backend(retriever: Any = None) -> None:
    """Set the knowledge retriever backend (called during app init)."""
    global _retriever  # noqa: PLW0603
    _retriever = retriever


class KnowledgeSearchTool:
    """Searches the knowledge store for relevant passages."""

    @property
    def name(self) -> str:
        return "knowledge_search"

    @property
    def description(self) -> str:
        return "Search ingested documents for relevant information"

    @property
    def permission_tier(self) -> int:
        return 0  # Safe, read-only

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    },
                },
                "required": ["query"],
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if _retriever is None:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="Knowledge store not configured.",
            )

        query = arguments.get("query", "")
        if not query:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="Query is required.",
            )

        passage = await _retriever.format_knowledge_block(query)
        if not passage:
            return ToolResult(
                tool_name=self.name,
                success=True,
                data={"passage": ""},
                display_text="No relevant documents found.",
            )

        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"passage": passage},
            display_text=passage,
        )
