"""Tests for intent router — regex-based intent classification."""

from __future__ import annotations

from cortex.agent.router import IntentPattern, IntentRouter
from cortex.agent.types import IntentType


class TestGreetingRouting:
    def test_pure_hello(self) -> None:
        router = IntentRouter()
        d = router.route("hello")
        assert d.intent_type == IntentType.GREETING

    def test_hey_there(self) -> None:
        router = IntentRouter()
        d = router.route("Hey there")
        assert d.intent_type == IntentType.GREETING

    def test_hi_cortex(self) -> None:
        router = IntentRouter()
        d = router.route("Hi Cortex!")
        assert d.intent_type == IntentType.GREETING

    def test_greeting_with_filler(self) -> None:
        router = IntentRouter()
        d = router.route("Hey there. can you hear me?")
        assert d.intent_type == IntentType.GREETING

    def test_greeting_how_are_you(self) -> None:
        router = IntentRouter()
        d = router.route("Hello, how are you?")
        assert d.intent_type == IntentType.GREETING

    def test_hi_is_this_working(self) -> None:
        router = IntentRouter()
        d = router.route("Hi there, is this working?")
        assert d.intent_type == IntentType.GREETING

    def test_greeting_with_real_question_falls_to_llm(self) -> None:
        """Greeting + real question should NOT match greeting."""
        router = IntentRouter()
        d = router.route("Hi, what time is it?")
        # Should NOT be greeting — it has a real question
        assert d.intent_type != IntentType.GREETING

    def test_greeting_with_factual_question_falls_to_llm(self) -> None:
        router = IntentRouter()
        d = router.route("Hey, why is the sky blue?")
        assert d.intent_type != IntentType.GREETING

    def test_good_morning(self) -> None:
        router = IntentRouter()
        d = router.route("Good morning")
        assert d.intent_type == IntentType.GREETING


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


class TestCalendarQueryRouting:
    def test_whats_on_my_calendar(self) -> None:
        router = IntentRouter()
        d = router.route("what's on my calendar")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match is not None
        assert d.intent_match.intent_id == "calendar_query"
        assert d.tool_hints == ["calendar_query"]

    def test_show_my_events(self) -> None:
        router = IntentRouter()
        d = router.route("show me my upcoming events")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "calendar_query"

    def test_check_my_calendar(self) -> None:
        router = IntentRouter()
        d = router.route("check my calendar")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "calendar_query"

    def test_do_i_have_meetings_today(self) -> None:
        router = IntentRouter()
        d = router.route("do I have any meetings today")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "calendar_query"

    def test_what_do_i_have_coming_up(self) -> None:
        router = IntentRouter()
        d = router.route("what do I have coming up")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "calendar_query"

    def test_any_upcoming_appointments(self) -> None:
        router = IntentRouter()
        d = router.route("any upcoming appointments")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "calendar_query"

    def test_list_my_schedule(self) -> None:
        router = IntentRouter()
        d = router.route("list my schedule")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "calendar_query"


class TestCalendarCreateRouting:
    def test_schedule_a_meeting(self) -> None:
        router = IntentRouter()
        d = router.route("schedule a meeting")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match is not None
        assert d.intent_match.intent_id == "calendar_create"
        assert d.tool_hints == ["calendar_create"]

    def test_create_an_event(self) -> None:
        router = IntentRouter()
        d = router.route("create an event")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "calendar_create"

    def test_add_to_my_calendar(self) -> None:
        router = IntentRouter()
        d = router.route("add something to my calendar")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "calendar_create"

    def test_book_an_appointment(self) -> None:
        router = IntentRouter()
        d = router.route("book an appointment")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "calendar_create"

    def test_set_up_a_meeting(self) -> None:
        router = IntentRouter()
        d = router.route("set up a meeting")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "calendar_create"


class TestEmailQueryRouting:
    def test_check_my_email(self) -> None:
        router = IntentRouter()
        d = router.route("check my email")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match is not None
        assert d.intent_match.intent_id == "email_query"
        assert d.tool_hints == ["email_query"]

    def test_any_new_emails(self) -> None:
        router = IntentRouter()
        d = router.route("any new emails")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "email_query"

    def test_show_my_inbox(self) -> None:
        router = IntentRouter()
        d = router.route("show my inbox")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "email_query"

    def test_unread_messages(self) -> None:
        router = IntentRouter()
        d = router.route("unread messages")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "email_query"


class TestEmailSendRouting:
    def test_send_an_email(self) -> None:
        router = IntentRouter()
        d = router.route("send an email")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match is not None
        assert d.intent_match.intent_id == "email_send"

    def test_compose_email(self) -> None:
        router = IntentRouter()
        d = router.route("compose an email")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "email_send"

    def test_write_a_message(self) -> None:
        router = IntentRouter()
        d = router.route("write a message")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "email_send"


class TestNotificationRouting:
    def test_send_notification(self) -> None:
        router = IntentRouter()
        d = router.route("send a notification")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match is not None
        assert d.intent_match.intent_id == "notification_send"
        assert d.tool_hints == ["notification_send_external"]

    def test_push_notification(self) -> None:
        router = IntentRouter()
        d = router.route("push a notification")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "notification_send"

    def test_notify_my_phone(self) -> None:
        router = IntentRouter()
        d = router.route("notify my phone")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "notification_send"

    def test_send_alert_to_phone(self) -> None:
        router = IntentRouter()
        d = router.route("send an alert to my phone")
        assert d.intent_type == IntentType.UTILITY
        assert d.intent_match.intent_id == "notification_send"


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

    def test_what_is_word_math_goes_to_llm(self) -> None:
        """'What is one plus one' should NOT match calculator or device_query."""
        router = IntentRouter()
        d = router.route("What is one plus one plus one plus 2")
        assert d.intent_type == IntentType.LLM

    def test_why_is_sky_blue_goes_to_llm(self) -> None:
        """'Why is the sky blue' should NOT match device_query."""
        router = IntentRouter()
        d = router.route("Why is the sky blue")
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
