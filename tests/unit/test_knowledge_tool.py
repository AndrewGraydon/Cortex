"""Tests for the knowledge_search cognitive tool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cortex.agent.tools.builtin.knowledge_tool import (
    KnowledgeSearchTool,
    set_knowledge_backend,
)


@pytest.fixture(autouse=True)
def _reset_backend() -> None:
    """Reset the module-level backend before each test."""
    set_knowledge_backend(None)


@pytest.fixture
def tool() -> KnowledgeSearchTool:
    return KnowledgeSearchTool()


class TestSchema:
    def test_name(self, tool: KnowledgeSearchTool) -> None:
        assert tool.name == "knowledge_search"

    def test_description(self, tool: KnowledgeSearchTool) -> None:
        assert "knowledge" in tool.description.lower() or "document" in tool.description.lower()

    def test_permission_tier(self, tool: KnowledgeSearchTool) -> None:
        assert tool.permission_tier == 0  # Safe, read-only

    def test_schema_has_query_param(self, tool: KnowledgeSearchTool) -> None:
        schema = tool.get_schema()
        assert "query" in schema["parameters"]["properties"]
        assert "query" in schema["parameters"]["required"]


class TestExecuteNoBackend:
    async def test_no_backend_returns_error(self, tool: KnowledgeSearchTool) -> None:
        result = await tool.execute({"query": "test"})
        assert result.success is False
        assert "not configured" in (result.error or "").lower()


class TestExecuteWithBackend:
    @pytest.fixture
    def mock_retriever(self) -> AsyncMock:
        retriever = AsyncMock()
        passage = "[Knowledge]\nSource: Doc\nContent here."
        retriever.format_knowledge_block = AsyncMock(return_value=passage)
        return retriever

    @pytest.fixture(autouse=True)
    def _set_backend(self, mock_retriever: AsyncMock) -> None:
        set_knowledge_backend(mock_retriever)

    async def test_successful_search(
        self, tool: KnowledgeSearchTool, mock_retriever: AsyncMock
    ) -> None:
        result = await tool.execute({"query": "test query"})
        assert result.success is True
        assert result.data is not None
        assert "Content here." in result.data["passage"]
        mock_retriever.format_knowledge_block.assert_awaited_once_with("test query")

    async def test_empty_query_returns_error(self, tool: KnowledgeSearchTool) -> None:
        result = await tool.execute({"query": ""})
        assert result.success is False
        assert "required" in (result.error or "").lower()

    async def test_missing_query_returns_error(self, tool: KnowledgeSearchTool) -> None:
        result = await tool.execute({})
        assert result.success is False

    async def test_no_results(self, tool: KnowledgeSearchTool, mock_retriever: AsyncMock) -> None:
        mock_retriever.format_knowledge_block.return_value = ""
        result = await tool.execute({"query": "obscure query"})
        assert result.success is True
        assert "No relevant" in (result.display_text or "")

    async def test_display_text_set(
        self, tool: KnowledgeSearchTool, mock_retriever: AsyncMock
    ) -> None:
        result = await tool.execute({"query": "test"})
        assert result.display_text is not None
        assert "Content here." in result.display_text
