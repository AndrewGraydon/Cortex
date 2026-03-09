"""Tests for proactive engine."""

from __future__ import annotations

import time

from cortex.agent.proactive.engine import ProactiveEngine
from cortex.agent.proactive.types import ProactiveType, RoutinePattern


def _make_pattern(
    content: str = "clock", hour: int = 8, day: int = 1, count: int = 10
) -> RoutinePattern:
    return RoutinePattern(
        event_type="tool_use",
        content=content,
        hour=hour,
        day_of_week=day,
        count=count,
    )


class TestShouldThink:
    def test_disabled(self) -> None:
        engine = ProactiveEngine(enabled=False)
        assert engine.should_think() is False

    def test_enabled_first_time(self) -> None:
        engine = ProactiveEngine(enabled=True, think_interval=0.0)
        assert engine.should_think() is True

    def test_too_soon(self) -> None:
        engine = ProactiveEngine(enabled=True, think_interval=300.0)
        engine._last_think = time.time()
        assert engine.should_think() is False


class TestGenerateCandidates:
    def test_generates_from_patterns(self) -> None:
        engine = ProactiveEngine(enabled=True)
        patterns = [_make_pattern(hour=8, day=1)]
        candidates = engine.generate_candidates(patterns, current_hour=8, current_day=1)
        assert len(candidates) == 1
        assert candidates[0].proactive_type == ProactiveType.ROUTINE_REMINDER

    def test_filters_by_time(self) -> None:
        engine = ProactiveEngine(enabled=True)
        patterns = [_make_pattern(hour=8, day=1)]
        candidates = engine.generate_candidates(patterns, current_hour=15, current_day=1)
        assert len(candidates) == 0

    def test_multiple_patterns(self) -> None:
        engine = ProactiveEngine(enabled=True)
        patterns = [
            _make_pattern(content="clock", hour=8, day=1),
            _make_pattern(content="weather", hour=8, day=1),
        ]
        candidates = engine.generate_candidates(patterns, current_hour=8, current_day=1)
        assert len(candidates) == 2

    def test_updates_last_think(self) -> None:
        engine = ProactiveEngine(enabled=True)
        before = time.time()
        engine.generate_candidates([], current_hour=8, current_day=1)
        assert engine._last_think >= before

    def test_candidate_has_pattern(self) -> None:
        engine = ProactiveEngine(enabled=True)
        pattern = _make_pattern()
        candidates = engine.generate_candidates([pattern], current_hour=8, current_day=1)
        assert candidates[0].pattern is pattern


class TestMarkDelivered:
    def test_mark_delivered(self) -> None:
        engine = ProactiveEngine(enabled=True)
        patterns = [_make_pattern()]
        candidates = engine.generate_candidates(patterns, current_hour=8, current_day=1)
        engine.mark_delivered(candidates[0])
        assert len(engine.candidates) == 0
        assert len(engine.delivered) == 1


class TestClear:
    def test_clear_all(self) -> None:
        engine = ProactiveEngine(enabled=True)
        patterns = [_make_pattern()]
        engine.generate_candidates(patterns, current_hour=8, current_day=1)
        engine.clear()
        assert len(engine.candidates) == 0
        assert len(engine.delivered) == 0


class TestProperties:
    def test_enabled(self) -> None:
        engine = ProactiveEngine(enabled=True)
        assert engine.enabled is True
        engine.enabled = False
        assert engine.enabled is False

    def test_think_interval(self) -> None:
        engine = ProactiveEngine(think_interval=600.0)
        assert engine.think_interval == 600.0
