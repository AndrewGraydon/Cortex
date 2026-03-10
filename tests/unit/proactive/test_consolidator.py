"""Tests for MemoryConsolidator — event summarization."""

from __future__ import annotations

import time

import pytest

from cortex.agent.proactive.consolidator import MemoryConsolidator, _generate_fact


class TestGenerateFact:
    def test_tool_use(self) -> None:
        fact = _generate_fact("tool_use", "clock", 10)
        assert "clock" in fact
        assert "tool" in fact.lower()
        assert "10" in fact

    def test_query_topic(self) -> None:
        fact = _generate_fact("query_topic", "weather", 5)
        assert "weather" in fact
        assert "asks" in fact.lower()

    def test_routine_action(self) -> None:
        fact = _generate_fact("routine_action", "morning coffee", 7)
        assert "morning coffee" in fact

    def test_unknown_type(self) -> None:
        fact = _generate_fact("other", "something", 3)
        assert "something" in fact
        assert "3" in fact


class TestMemoryConsolidator:
    @pytest.fixture()
    def consolidator(self) -> MemoryConsolidator:
        return MemoryConsolidator(min_events=3, cooldown_seconds=0.0)

    def test_should_run_initially(self, consolidator: MemoryConsolidator) -> None:
        assert consolidator.should_run() is True

    def test_should_run_cooldown(self) -> None:
        c = MemoryConsolidator(cooldown_seconds=3600.0)
        c._last_run = time.time()
        assert c.should_run() is False

    @pytest.mark.asyncio()
    async def test_empty_events(self, consolidator: MemoryConsolidator) -> None:
        facts = await consolidator.consolidate([])
        assert facts == []

    @pytest.mark.asyncio()
    async def test_below_threshold(self, consolidator: MemoryConsolidator) -> None:
        events = [
            {"event_type": "tool_use", "content": "clock", "timestamp": 1000.0},
            {"event_type": "tool_use", "content": "clock", "timestamp": 1001.0},
        ]
        facts = await consolidator.consolidate(events)
        assert facts == []  # Only 2, need 3

    @pytest.mark.asyncio()
    async def test_generates_facts(self, consolidator: MemoryConsolidator) -> None:
        events = [
            {"event_type": "tool_use", "content": "clock", "timestamp": float(i)}
            for i in range(5)
        ]
        facts = await consolidator.consolidate(events)
        assert len(facts) == 1
        assert "clock" in facts[0]

    @pytest.mark.asyncio()
    async def test_multiple_groups(self, consolidator: MemoryConsolidator) -> None:
        events = [
            {"event_type": "tool_use", "content": "clock", "timestamp": float(i)}
            for i in range(5)
        ] + [
            {"event_type": "query_topic", "content": "weather", "timestamp": float(i)}
            for i in range(4)
        ]
        facts = await consolidator.consolidate(events)
        assert len(facts) == 2

    @pytest.mark.asyncio()
    async def test_updates_last_run(self, consolidator: MemoryConsolidator) -> None:
        assert consolidator.last_run == 0.0
        await consolidator.consolidate([])
        assert consolidator.last_run > 0

    @pytest.mark.asyncio()
    async def test_with_memory_store(self) -> None:
        from unittest.mock import AsyncMock

        mock_store = AsyncMock()
        mock_store.store_fact = AsyncMock()
        consolidator = MemoryConsolidator(
            memory_store=mock_store, min_events=2, cooldown_seconds=0.0,
        )
        events = [
            {"event_type": "tool_use", "content": "clock", "timestamp": float(i)}
            for i in range(3)
        ]
        facts = await consolidator.consolidate(events)
        assert len(facts) == 1
        assert mock_store.store_fact.call_count == 1
        assert consolidator.facts_generated == 1

    @pytest.mark.asyncio()
    async def test_idempotent(self, consolidator: MemoryConsolidator) -> None:
        events = [
            {"event_type": "tool_use", "content": "clock", "timestamp": float(i)}
            for i in range(5)
        ]
        facts1 = await consolidator.consolidate(events)
        facts2 = await consolidator.consolidate(events)
        assert facts1 == facts2
