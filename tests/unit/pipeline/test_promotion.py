"""Tests for tool promotion tracker."""

from __future__ import annotations

import pytest

from cortex.agent.tools.pipeline.promotion import ToolPromotionTracker


@pytest.fixture
async def tracker(tmp_path) -> ToolPromotionTracker:
    t = ToolPromotionTracker(
        db_path=str(tmp_path / "promotion.db"),
        promotion_threshold=3,
    )
    await t.start()
    yield t
    await t.stop()


class TestRecordExecution:
    async def test_record_success(self, tracker: ToolPromotionTracker) -> None:
        await tracker.record_execution("my-tool", success=True)
        stats = await tracker.get_stats("my-tool")
        assert stats is not None
        assert stats["total_executions"] == 1
        assert stats["successful_executions"] == 1
        assert stats["consecutive_successes"] == 1

    async def test_record_failure(self, tracker: ToolPromotionTracker) -> None:
        await tracker.record_execution("my-tool", success=False)
        stats = await tracker.get_stats("my-tool")
        assert stats is not None
        assert stats["failed_executions"] == 1
        assert stats["consecutive_successes"] == 0

    async def test_failure_resets_consecutive(self, tracker: ToolPromotionTracker) -> None:
        await tracker.record_execution("my-tool", success=True)
        await tracker.record_execution("my-tool", success=True)
        await tracker.record_execution("my-tool", success=False)
        stats = await tracker.get_stats("my-tool")
        assert stats is not None
        assert stats["consecutive_successes"] == 0
        assert stats["total_executions"] == 3

    async def test_multiple_tools(self, tracker: ToolPromotionTracker) -> None:
        await tracker.record_execution("tool-a", success=True)
        await tracker.record_execution("tool-b", success=True)
        stats_a = await tracker.get_stats("tool-a")
        stats_b = await tracker.get_stats("tool-b")
        assert stats_a is not None
        assert stats_b is not None
        assert stats_a["total_executions"] == 1
        assert stats_b["total_executions"] == 1


class TestPromotion:
    async def test_not_eligible_initially(self, tracker: ToolPromotionTracker) -> None:
        await tracker.record_execution("my-tool", success=True)
        assert await tracker.check_promotion_eligible("my-tool") is False

    async def test_eligible_after_threshold(self, tracker: ToolPromotionTracker) -> None:
        for _ in range(3):
            await tracker.record_execution("my-tool", success=True)
        assert await tracker.check_promotion_eligible("my-tool") is True

    async def test_promote_reduces_tier(self, tracker: ToolPromotionTracker) -> None:
        for _ in range(3):
            await tracker.record_execution("my-tool", success=True)
        promoted = await tracker.promote("my-tool")
        assert promoted is True
        stats = await tracker.get_stats("my-tool")
        assert stats is not None
        assert stats["current_tier"] == 1

    async def test_promote_resets_consecutive(self, tracker: ToolPromotionTracker) -> None:
        for _ in range(3):
            await tracker.record_execution("my-tool", success=True)
        await tracker.promote("my-tool")
        stats = await tracker.get_stats("my-tool")
        assert stats is not None
        assert stats["consecutive_successes"] == 0

    async def test_promote_not_eligible(self, tracker: ToolPromotionTracker) -> None:
        await tracker.record_execution("my-tool", success=True)
        promoted = await tracker.promote("my-tool")
        assert promoted is False

    async def test_promote_unknown_tool(self, tracker: ToolPromotionTracker) -> None:
        promoted = await tracker.promote("nonexistent")
        assert promoted is False

    async def test_cannot_promote_below_tier_1(self, tracker: ToolPromotionTracker) -> None:
        # Get to tier 1 first
        for _ in range(3):
            await tracker.record_execution("my-tool", success=True)
        await tracker.promote("my-tool")
        # Try to promote again — tier 1 cannot go lower
        for _ in range(3):
            await tracker.record_execution("my-tool", success=True)
        assert await tracker.check_promotion_eligible("my-tool") is False


class TestDemote:
    async def test_demote(self, tracker: ToolPromotionTracker) -> None:
        for _ in range(3):
            await tracker.record_execution("my-tool", success=True)
        await tracker.promote("my-tool")
        await tracker.demote("my-tool", tier=2)
        stats = await tracker.get_stats("my-tool")
        assert stats is not None
        assert stats["current_tier"] == 2


class TestListAll:
    async def test_list_empty(self, tracker: ToolPromotionTracker) -> None:
        result = await tracker.list_all()
        assert result == []

    async def test_list_multiple(self, tracker: ToolPromotionTracker) -> None:
        await tracker.record_execution("tool-a", success=True)
        await tracker.record_execution("tool-b", success=False)
        result = await tracker.list_all()
        assert len(result) == 2


class TestLifecycle:
    async def test_not_started_raises(self) -> None:
        tracker = ToolPromotionTracker(db_path=":memory:")
        with pytest.raises(RuntimeError, match="not started"):
            await tracker.record_execution("x", success=True)

    async def test_get_stats_unknown(self, tracker: ToolPromotionTracker) -> None:
        stats = await tracker.get_stats("nonexistent")
        assert stats is None

    def test_promotion_threshold_property(self, tracker: ToolPromotionTracker) -> None:
        assert tracker.promotion_threshold == 3
