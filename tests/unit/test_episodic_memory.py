"""Tests for episodic memory store — event recording, querying, and patterns."""

from __future__ import annotations

import time

import pytest

from cortex.memory.episodic import EpisodicMemoryStore
from cortex.memory.migration import MIGRATION_V2
from cortex.memory.types import EventType


@pytest.fixture
async def store(tmp_path: object) -> EpisodicMemoryStore:
    """Create an episodic store backed by a temp DB with schema already applied."""
    import aiosqlite

    db_path = str(tmp_path) + "/test_episodic.db"  # type: ignore[operator]
    # Create the schema manually since EpisodicMemoryStore doesn't create tables
    db = await aiosqlite.connect(db_path)
    await db.executescript(MIGRATION_V2)
    await db.commit()
    await db.close()

    s = EpisodicMemoryStore(db_path=db_path)
    await s.start()
    yield s  # type: ignore[misc]
    await s.stop()


class TestRecordEvent:
    async def test_record_basic_event(self, store: EpisodicMemoryStore) -> None:
        event = await store.record_event(EventType.TOOL_USE, "clock", session_id="sess-1")
        assert event.event_type == EventType.TOOL_USE
        assert event.content == "clock"
        assert event.session_id == "sess-1"
        assert event.id  # Non-empty

    async def test_record_with_metadata(self, store: EpisodicMemoryStore) -> None:
        event = await store.record_event(
            EventType.TOOL_USE,
            "calculator",
            metadata={"arguments": '{"expr": "2+2"}'},
        )
        assert event.metadata["arguments"] == '{"expr": "2+2"}'

    async def test_record_with_custom_timestamp(self, store: EpisodicMemoryStore) -> None:
        ts = 1700000000.0
        event = await store.record_event(EventType.SESSION_START, "start", timestamp=ts)
        assert event.timestamp == ts

    async def test_record_multiple_events(self, store: EpisodicMemoryStore) -> None:
        for i in range(5):
            await store.record_event(EventType.QUERY_TOPIC, f"topic-{i}")
        count = await store.event_count()
        assert count == 5


class TestQueryEvents:
    async def test_query_all(self, store: EpisodicMemoryStore) -> None:
        await store.record_event(EventType.TOOL_USE, "clock")
        await store.record_event(EventType.QUERY_TOPIC, "weather")
        events = await store.query_events()
        assert len(events) == 2

    async def test_query_by_type(self, store: EpisodicMemoryStore) -> None:
        await store.record_event(EventType.TOOL_USE, "clock")
        await store.record_event(EventType.QUERY_TOPIC, "weather")
        await store.record_event(EventType.TOOL_USE, "calculator")
        events = await store.query_events(event_type=EventType.TOOL_USE)
        assert len(events) == 2
        assert all(e.event_type == EventType.TOOL_USE for e in events)

    async def test_query_by_time_range(self, store: EpisodicMemoryStore) -> None:
        old_ts = time.time() - 86400  # 1 day ago
        new_ts = time.time()
        await store.record_event(EventType.TOOL_USE, "old-tool", timestamp=old_ts)
        await store.record_event(EventType.TOOL_USE, "new-tool", timestamp=new_ts)

        events = await store.query_events(since=new_ts - 1)
        assert len(events) == 1
        assert events[0].content == "new-tool"

    async def test_query_limit(self, store: EpisodicMemoryStore) -> None:
        for i in range(10):
            await store.record_event(EventType.TOOL_USE, f"tool-{i}")
        events = await store.query_events(limit=3)
        assert len(events) == 3

    async def test_query_ordered_by_timestamp_desc(self, store: EpisodicMemoryStore) -> None:
        await store.record_event(EventType.TOOL_USE, "first", timestamp=1000.0)
        await store.record_event(EventType.TOOL_USE, "second", timestamp=2000.0)
        events = await store.query_events()
        assert events[0].content == "second"  # Newest first

    async def test_query_empty(self, store: EpisodicMemoryStore) -> None:
        events = await store.query_events()
        assert events == []


class TestEventCount:
    async def test_count_all(self, store: EpisodicMemoryStore) -> None:
        assert await store.event_count() == 0
        await store.record_event(EventType.TOOL_USE, "clock")
        assert await store.event_count() == 1

    async def test_count_by_type(self, store: EpisodicMemoryStore) -> None:
        await store.record_event(EventType.TOOL_USE, "clock")
        await store.record_event(EventType.QUERY_TOPIC, "weather")
        assert await store.event_count(EventType.TOOL_USE) == 1
        assert await store.event_count(EventType.QUERY_TOPIC) == 1


class TestRoutinePatterns:
    async def test_no_events_no_patterns(self, store: EpisodicMemoryStore) -> None:
        patterns = await store.get_routine_patterns()
        assert patterns == []

    async def test_below_threshold_ignored(self, store: EpisodicMemoryStore) -> None:
        # Only 3 events — below min_occurrences=5
        for _ in range(3):
            await store.record_event(EventType.TOOL_USE, "clock")
        patterns = await store.get_routine_patterns(min_occurrences=5)
        assert patterns == []

    async def test_detects_routine(self, store: EpisodicMemoryStore) -> None:
        # Record 10 events at the same time (recent, within days_back window)
        base_ts = time.time() - 3600  # 1 hour ago
        for i in range(10):
            await store.record_event(EventType.TOOL_USE, "clock", timestamp=base_ts + i)
        patterns = await store.get_routine_patterns(min_occurrences=5, days_back=30)
        assert len(patterns) >= 1
        assert patterns[0]["content"] == "clock"
        assert patterns[0]["count"] >= 5

    async def test_groups_by_hour_and_day(self, store: EpisodicMemoryStore) -> None:
        # Events at the same hour today
        base_ts = time.time() - 3600
        for i in range(6):
            await store.record_event(EventType.TOOL_USE, "clock", timestamp=base_ts + i)
        # Different day events (3 days ago, likely different day_of_week)
        diff_ts = base_ts - 86400 * 3
        for i in range(6):
            await store.record_event(EventType.TOOL_USE, "clock", timestamp=diff_ts + i)
        patterns = await store.get_routine_patterns(min_occurrences=5, days_back=30)
        # Should detect patterns grouped by day
        assert len(patterns) >= 1


class TestPruneEvents:
    async def test_prune_old_events(self, store: EpisodicMemoryStore) -> None:
        old_ts = time.time() - (400 * 86400)  # 400 days ago
        await store.record_event(EventType.TOOL_USE, "old", timestamp=old_ts)
        await store.record_event(EventType.TOOL_USE, "new")

        deleted = await store.prune_old_events(max_age_days=365)
        assert deleted == 1
        assert await store.event_count() == 1

    async def test_prune_nothing(self, store: EpisodicMemoryStore) -> None:
        await store.record_event(EventType.TOOL_USE, "recent")
        deleted = await store.prune_old_events(max_age_days=365)
        assert deleted == 0


class TestLifecycle:
    async def test_not_started_raises(self) -> None:
        s = EpisodicMemoryStore(db_path=":memory:")
        with pytest.raises(RuntimeError, match="not started"):
            await s.event_count()
