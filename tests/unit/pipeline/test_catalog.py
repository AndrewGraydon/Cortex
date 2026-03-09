"""Tests for tool catalog."""

from __future__ import annotations

import pytest

from cortex.agent.tools.pipeline.catalog import ToolCatalog
from cortex.agent.tools.pipeline.types import PipelineStage


@pytest.fixture
async def catalog(tmp_path) -> ToolCatalog:
    c = ToolCatalog(db_path=str(tmp_path / "catalog.db"))
    await c.start()
    yield c
    await c.stop()


class TestAdd:
    async def test_add_tool(self, catalog: ToolCatalog) -> None:
        await catalog.add(name="my-tool", description="Test tool")
        entry = await catalog.get("my-tool")
        assert entry is not None
        assert entry["name"] == "my-tool"
        assert entry["description"] == "Test tool"

    async def test_add_with_source(self, catalog: ToolCatalog) -> None:
        await catalog.add(name="my-tool", description="Test", source="user")
        entry = await catalog.get("my-tool")
        assert entry is not None
        assert entry["source"] == "user"

    async def test_add_with_stage(self, catalog: ToolCatalog) -> None:
        await catalog.add(name="my-tool", description="Test", stage=PipelineStage.APPROVED)
        entry = await catalog.get("my-tool")
        assert entry is not None
        assert entry["stage"] == "approved"

    async def test_add_replaces_existing(self, catalog: ToolCatalog) -> None:
        await catalog.add(name="my-tool", description="First")
        await catalog.add(name="my-tool", description="Second")
        entry = await catalog.get("my-tool")
        assert entry is not None
        assert entry["description"] == "Second"


class TestUpdateStage:
    async def test_update_stage(self, catalog: ToolCatalog) -> None:
        await catalog.add(name="my-tool", description="Test")
        updated = await catalog.update_stage("my-tool", PipelineStage.DEPLOYED)
        assert updated is True
        entry = await catalog.get("my-tool")
        assert entry is not None
        assert entry["stage"] == "deployed"

    async def test_update_nonexistent(self, catalog: ToolCatalog) -> None:
        updated = await catalog.update_stage("nonexistent", PipelineStage.DEPLOYED)
        assert updated is False


class TestIncrementUsage:
    async def test_increment(self, catalog: ToolCatalog) -> None:
        await catalog.add(name="my-tool", description="Test")
        await catalog.increment_usage("my-tool")
        await catalog.increment_usage("my-tool")
        entry = await catalog.get("my-tool")
        assert entry is not None
        assert entry["usage_count"] == 2


class TestListAll:
    async def test_empty(self, catalog: ToolCatalog) -> None:
        result = await catalog.list_all()
        assert result == []

    async def test_list_multiple(self, catalog: ToolCatalog) -> None:
        await catalog.add(name="tool-a", description="A")
        await catalog.add(name="tool-b", description="B")
        result = await catalog.list_all()
        assert len(result) == 2

    async def test_filter_by_source(self, catalog: ToolCatalog) -> None:
        await catalog.add(name="tool-a", description="A", source="user")
        await catalog.add(name="tool-b", description="B", source="builtin")
        result = await catalog.list_all(source="user")
        assert len(result) == 1
        assert result[0]["name"] == "tool-a"

    async def test_filter_by_stage(self, catalog: ToolCatalog) -> None:
        await catalog.add(name="tool-a", description="A", stage=PipelineStage.DRAFT)
        await catalog.add(name="tool-b", description="B", stage=PipelineStage.DEPLOYED)
        result = await catalog.list_all(stage=PipelineStage.DEPLOYED)
        assert len(result) == 1
        assert result[0]["name"] == "tool-b"


class TestRemove:
    async def test_remove_existing(self, catalog: ToolCatalog) -> None:
        await catalog.add(name="my-tool", description="Test")
        removed = await catalog.remove("my-tool")
        assert removed is True
        assert await catalog.get("my-tool") is None

    async def test_remove_nonexistent(self, catalog: ToolCatalog) -> None:
        removed = await catalog.remove("nonexistent")
        assert removed is False


class TestCount:
    async def test_count_empty(self, catalog: ToolCatalog) -> None:
        assert await catalog.count() == 0

    async def test_count_all(self, catalog: ToolCatalog) -> None:
        await catalog.add(name="tool-a", description="A")
        await catalog.add(name="tool-b", description="B")
        assert await catalog.count() == 2

    async def test_count_by_source(self, catalog: ToolCatalog) -> None:
        await catalog.add(name="tool-a", description="A", source="user")
        await catalog.add(name="tool-b", description="B", source="builtin")
        assert await catalog.count(source="user") == 1


class TestLifecycle:
    async def test_not_started_raises(self) -> None:
        catalog = ToolCatalog(db_path=":memory:")
        with pytest.raises(RuntimeError, match="not started"):
            await catalog.get("x")

    async def test_get_nonexistent(self, catalog: ToolCatalog) -> None:
        assert await catalog.get("nonexistent") is None
