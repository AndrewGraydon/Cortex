"""Tests for intent router — regex-based intent classification."""

from __future__ import annotations

from cortex.agent.router import IntentPattern, IntentRouter
from cortex.agent.types import IntentType


class TestFarewellRouting:
    def test_goodbye(self) -> None:
        router = IntentRouter()
        d = router.route("goodbye")
        assert d.intent_type == IntentType.FAREWELL

    def test_bye(self) -> None:
        router = IntentRouter()
        d = router.route("bye")
        assert d.intent_type == IntentType.FAREWELL

    def test_thanks_bye(self) -> None:
        router = IntentRouter()
        d = router.route("thanks bye")
        assert d.intent_type == IntentType.FAREWELL

    def test_stop(self) -> None:
        router = IntentRouter()
        d = router.route("stop")
        assert d.intent_type == IntentType.FAREWELL

    def test_not_farewell(self) -> None:
        router = IntentRouter()
        d = router.route("tell me about goodbyes in different cultures")
        assert d.intent_type != IntentType.FAREWELL


class TestClockRouting:
    def test_what_time_is_it(self) -> None:
        router = IntentRouter()
        d = router.route("what time is it")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match is not None
        assert d.intent_match.intent_id == "clock"
        assert d.tool_hints == ["clock"]

    def test_whats_the_time(self) -> None:
        router = IntentRouter()
        d = router.route("what's the time?")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "clock"

    def test_current_date(self) -> None:
        router = IntentRouter()
        d = router.route("what is the date today")
        assert d.intent_type == IntentType.UTILITY

    def test_what_day_is_it(self) -> None:
        router = IntentRouter()
        d = router.route("what day is it")
        assert d.intent_type == IntentType.UTILITY


class TestTimerRouting:
    def test_set_timer_minutes(self) -> None:
        router = IntentRouter()
        d = router.route("set a timer for 5 minutes")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "timer_set"
        assert d.intent_match.extracted["duration"] == "5"
        assert "minute" in d.intent_match.extracted["unit"]

    def test_set_timer_seconds(self) -> None:
        router = IntentRouter()
        d = router.route("set timer for 30 seconds")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.extracted["duration"] == "30"

    def test_timer_query(self) -> None:
        router = IntentRouter()
        d = router.route("check my timers")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "timer_query"

    def test_how_much_time_left(self) -> None:
        router = IntentRouter()
        d = router.route("how much time is left on the timer")
        assert d.intent_type == IntentType.UTILITY


class TestCalculatorRouting:
    def test_what_is_math(self) -> None:
        router = IntentRouter()
        d = router.route("what is 42 * 17")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "calculator"
        assert "42" in d.intent_match.extracted.get("expression", "")

    def test_calculate(self) -> None:
        router = IntentRouter()
        d = router.route("calculate 100 + 200")
        assert d.intent_type == IntentType.UTILITY

    def test_whats_addition(self) -> None:
        router = IntentRouter()
        d = router.route("what's 15 + 27")
        assert d.intent_type == IntentType.UTILITY


class TestSystemInfoRouting:
    def test_system_status(self) -> None:
        router = IntentRouter()
        d = router.route("system status")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "system_info"

    def test_device_check(self) -> None:
        router = IntentRouter()
        d = router.route("device health check")
        assert d.intent_type == IntentType.UTILITY


class TestMemorySaveRouting:
    def test_remember_that(self) -> None:
        router = IntentRouter()
        d = router.route("remember that my favorite color is blue")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "memory_save"
        assert "blue" in d.intent_match.extracted.get("fact", "")

    def test_my_name_is(self) -> None:
        router = IntentRouter()
        d = router.route("my name is Andrew")
        assert d.intent_type == IntentType.UTILITY
        assert "Andrew" in d.intent_match.extracted.get("fact", "")


class TestLLMFallback:
    def test_general_question(self) -> None:
        router = IntentRouter()
        d = router.route("tell me about the history of computing")
        assert d.intent_type == IntentType.LLM
        assert d.intent_match is None

    def test_empty_text(self) -> None:
        router = IntentRouter()
        d = router.route("")
        assert d.intent_type == IntentType.LLM

    def test_ambiguous_text(self) -> None:
        router = IntentRouter()
        d = router.route("how do I cook pasta")
        assert d.intent_type == IntentType.LLM


class TestCustomPatterns:
    def test_add_custom_pattern(self) -> None:
        router = IntentRouter()
        router.add_pattern(
            IntentPattern(
                "weather",
                IntentType.UTILITY,
                [r"(weather|forecast|temperature)\s*(today|tomorrow)?"],
                tool_hint="weather",
            )
        )
        d = router.route("weather today")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "weather"
