"""Tests for pattern detector."""

from __future__ import annotations

from cortex.agent.proactive.detector import PatternDetector


class TestDetectPatterns:
    def test_empty_input(self) -> None:
        detector = PatternDetector(min_occurrences=3)
        patterns = detector.detect_patterns([])
        assert patterns == []

    def test_below_threshold(self) -> None:
        detector = PatternDetector(min_occurrences=5)
        raw = [
            {"event_type": "tool_use", "content": "clock", "hour": 8, "day_of_week": 1, "count": 3}
        ]
        patterns = detector.detect_patterns(raw)
        assert len(patterns) == 0

    def test_above_threshold(self) -> None:
        detector = PatternDetector(min_occurrences=5)
        raw = [
            {"event_type": "tool_use", "content": "clock", "hour": 8, "day_of_week": 1, "count": 10}
        ]
        patterns = detector.detect_patterns(raw)
        assert len(patterns) == 1
        assert patterns[0].content == "clock"
        assert patterns[0].hour == 8

    def test_exactly_at_threshold(self) -> None:
        detector = PatternDetector(min_occurrences=5)
        raw = [
            {"event_type": "tool_use", "content": "clock", "hour": 8, "day_of_week": 1, "count": 5}
        ]
        patterns = detector.detect_patterns(raw)
        assert len(patterns) == 1

    def test_sorted_by_count(self) -> None:
        detector = PatternDetector(min_occurrences=3)
        raw = [
            {"event_type": "tool_use", "content": "clock", "hour": 8, "day_of_week": 1, "count": 5},
            {
                "event_type": "tool_use",
                "content": "weather",
                "hour": 9,
                "day_of_week": 1,
                "count": 10,
            },
        ]
        patterns = detector.detect_patterns(raw)
        assert len(patterns) == 2
        assert patterns[0].content == "weather"
        assert patterns[1].content == "clock"

    def test_confidence_calculated(self) -> None:
        detector = PatternDetector(min_occurrences=1, days_back=30)
        raw = [
            {"event_type": "tool_use", "content": "clock", "hour": 8, "day_of_week": 1, "count": 15}
        ]
        patterns = detector.detect_patterns(raw)
        assert patterns[0].confidence == 0.5  # 15/30

    def test_confidence_capped_at_1(self) -> None:
        detector = PatternDetector(min_occurrences=1, days_back=10)
        raw = [
            {"event_type": "tool_use", "content": "clock", "hour": 8, "day_of_week": 1, "count": 20}
        ]
        patterns = detector.detect_patterns(raw)
        assert patterns[0].confidence == 1.0

    def test_multiple_types(self) -> None:
        detector = PatternDetector(min_occurrences=3)
        raw = [
            {"event_type": "tool_use", "content": "clock", "hour": 8, "day_of_week": 1, "count": 5},
            {
                "event_type": "query_topic",
                "content": "weather",
                "hour": 8,
                "day_of_week": 1,
                "count": 7,
            },
        ]
        patterns = detector.detect_patterns(raw)
        assert len(patterns) == 2


class TestFilterForTime:
    def test_matching_time(self) -> None:
        detector = PatternDetector(min_occurrences=3)
        raw = [
            {"event_type": "tool_use", "content": "clock", "hour": 8, "day_of_week": 1, "count": 5}
        ]
        patterns = detector.detect_patterns(raw)
        filtered = detector.filter_for_time(patterns, current_hour=8, current_day=1)
        assert len(filtered) == 1

    def test_adjacent_hour_matches(self) -> None:
        detector = PatternDetector(min_occurrences=3)
        raw = [
            {"event_type": "tool_use", "content": "clock", "hour": 8, "day_of_week": 1, "count": 5}
        ]
        patterns = detector.detect_patterns(raw)
        filtered = detector.filter_for_time(patterns, current_hour=9, current_day=1)
        assert len(filtered) == 1

    def test_wrong_day_excluded(self) -> None:
        detector = PatternDetector(min_occurrences=3)
        raw = [
            {"event_type": "tool_use", "content": "clock", "hour": 8, "day_of_week": 1, "count": 5}
        ]
        patterns = detector.detect_patterns(raw)
        filtered = detector.filter_for_time(patterns, current_hour=8, current_day=3)
        assert len(filtered) == 0

    def test_distant_hour_excluded(self) -> None:
        detector = PatternDetector(min_occurrences=3)
        raw = [
            {"event_type": "tool_use", "content": "clock", "hour": 8, "day_of_week": 1, "count": 5}
        ]
        patterns = detector.detect_patterns(raw)
        filtered = detector.filter_for_time(patterns, current_hour=15, current_day=1)
        assert len(filtered) == 0


class TestProperties:
    def test_min_occurrences(self) -> None:
        detector = PatternDetector(min_occurrences=10)
        assert detector.min_occurrences == 10

    def test_days_back(self) -> None:
        detector = PatternDetector(days_back=60)
        assert detector.days_back == 60
