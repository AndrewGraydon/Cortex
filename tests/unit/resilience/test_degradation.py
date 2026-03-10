"""Tests for degradation engine — all 8 DD-033 scenarios + combined failures."""

from __future__ import annotations

from cortex.resilience.circuit_breaker import CircuitBreaker
from cortex.resilience.degradation import DegradationEngine, DegradationState


class TestDegradationStateDefaults:
    """Initial DegradationState should be fully operational."""

    def test_all_true_by_default(self) -> None:
        state = DegradationState()
        assert state.llm_available is True
        assert state.tts_available is True
        assert state.asr_available is True
        assert state.network_available is True
        assert state.storage_ok is True
        assert state.power_ok is True

    def test_is_fully_operational(self) -> None:
        state = DegradationState()
        assert state.is_fully_operational is True

    def test_not_fully_operational_when_degraded(self) -> None:
        state = DegradationState(llm_available=False)
        assert state.is_fully_operational is False

    def test_user_messages_empty(self) -> None:
        state = DegradationState()
        assert state.user_messages == []


class TestDegradationDD033Scenarios:
    """All 8 DD-033 failure scenarios, individually."""

    def test_all_llm_fail_regex_fallback(self) -> None:
        """DD-033 #1: All LLM providers fail → regex-only fallback."""
        engine = DegradationEngine()
        llm_breaker = CircuitBreaker("llm", failure_threshold=1)
        llm_breaker.force_open()

        state = engine.evaluate(breakers={"llm": llm_breaker})
        assert state.llm_available is False
        assert "timers" in state.user_messages[0].lower()

    def test_tts_fail_lcd_fallback(self) -> None:
        """DD-033 #2: TTS fails → response on LCD."""
        engine = DegradationEngine()
        tts_breaker = CircuitBreaker("tts", failure_threshold=1)
        tts_breaker.force_open()

        state = engine.evaluate(breakers={"tts": tts_breaker})
        assert state.tts_available is False
        assert "screen" in state.user_messages[0].lower()

    def test_asr_fail_web_ui_message(self) -> None:
        """DD-033 #3: ASR fails → 'use web UI'."""
        engine = DegradationEngine()
        asr_breaker = CircuitBreaker("asr", failure_threshold=1)
        asr_breaker.force_open()

        state = engine.evaluate(breakers={"asr": asr_breaker})
        assert state.asr_available is False
        assert "web ui" in state.user_messages[0].lower()

    def test_network_down_local_continues(self) -> None:
        """DD-033 #4: Network down → local ops continue."""
        engine = DegradationEngine()
        state = engine.evaluate(network_ok=False)
        assert state.network_available is False
        assert "local" in state.user_messages[0].lower()

    def test_battery_low(self) -> None:
        """DD-033 #5: Battery < 15% → reduce brightness, warn user."""
        engine = DegradationEngine(battery_low_pct=15.0)
        state = engine.evaluate(battery_pct=12.0)
        assert state.power_ok is False
        assert "low" in state.user_messages[0].lower()

    def test_battery_critical(self) -> None:
        """DD-033 #6: Battery < 5% → clean shutdown."""
        engine = DegradationEngine(battery_critical_pct=5.0)
        state = engine.evaluate(battery_pct=3.0)
        assert state.power_ok is False
        assert "critical" in state.user_messages[0].lower()

    def test_storage_full(self) -> None:
        """DD-033 #7: Storage > 95% → disable audit writes."""
        engine = DegradationEngine(storage_full_pct=95.0)
        state = engine.evaluate(health={"storage": {"used_pct": 97.0}})
        assert state.storage_ok is False
        assert "storage" in state.user_messages[0].lower()

    def test_npu_throttle(self) -> None:
        """DD-033 #8a: NPU temp > 75°C → throttle warning."""
        engine = DegradationEngine(npu_throttle_temp=75.0)
        state = engine.evaluate(health={"npu": {"temp_c": 78.0}})
        assert "cool down" in state.user_messages[0].lower()
        # Services still available during throttle
        assert state.llm_available is True

    def test_npu_overheat_shutdown(self) -> None:
        """DD-033 #8b: NPU temp > 85°C → emergency stop."""
        engine = DegradationEngine(npu_shutdown_temp=85.0)
        state = engine.evaluate(health={"npu": {"temp_c": 90.0}})
        assert state.llm_available is False
        assert state.tts_available is False
        assert state.asr_available is False
        assert "too hot" in state.user_messages[0].lower()


class TestDegradationCombinedFailures:
    """Multiple simultaneous failures."""

    def test_llm_and_tts_both_fail(self) -> None:
        """Compound failure: regex fallback + LCD text."""
        engine = DegradationEngine()
        llm_breaker = CircuitBreaker("llm", failure_threshold=1)
        llm_breaker.force_open()
        tts_breaker = CircuitBreaker("tts", failure_threshold=1)
        tts_breaker.force_open()

        state = engine.evaluate(breakers={"llm": llm_breaker, "tts": tts_breaker})
        assert state.llm_available is False
        assert state.tts_available is False
        assert len(state.user_messages) == 2
        assert state.is_fully_operational is False

    def test_network_down_and_storage_full(self) -> None:
        engine = DegradationEngine()
        state = engine.evaluate(
            network_ok=False,
            health={"storage": {"used_pct": 98.0}},
        )
        assert state.network_available is False
        assert state.storage_ok is False
        assert len(state.user_messages) == 2

    def test_all_services_down(self) -> None:
        """Worst case: everything fails."""
        engine = DegradationEngine()
        breakers = {
            "llm": CircuitBreaker("llm", failure_threshold=1),
            "tts": CircuitBreaker("tts", failure_threshold=1),
            "asr": CircuitBreaker("asr", failure_threshold=1),
        }
        for b in breakers.values():
            b.force_open()

        state = engine.evaluate(
            breakers=breakers,
            network_ok=False,
            battery_pct=3.0,
            health={"storage": {"used_pct": 99.0}},
        )
        assert state.is_fully_operational is False
        assert state.llm_available is False
        assert state.tts_available is False
        assert state.asr_available is False
        assert state.network_available is False
        assert state.storage_ok is False
        assert state.power_ok is False


class TestDegradationRecovery:
    """System recovers when conditions improve."""

    def test_breaker_close_restores_service(self) -> None:
        engine = DegradationEngine()
        llm_breaker = CircuitBreaker("llm", failure_threshold=1)
        llm_breaker.force_open()

        state1 = engine.evaluate(breakers={"llm": llm_breaker})
        assert state1.llm_available is False

        llm_breaker.reset()
        state2 = engine.evaluate(breakers={"llm": llm_breaker})
        assert state2.llm_available is True
        assert state2.is_fully_operational is True

    def test_network_recovery(self) -> None:
        engine = DegradationEngine()
        state1 = engine.evaluate(network_ok=False)
        assert state1.network_available is False

        state2 = engine.evaluate(network_ok=True)
        assert state2.network_available is True

    def test_battery_recovery_on_mains(self) -> None:
        engine = DegradationEngine()
        state1 = engine.evaluate(battery_pct=10.0)
        assert state1.power_ok is False

        # None = mains power
        state2 = engine.evaluate(battery_pct=None)
        assert state2.power_ok is True


class TestDegradationCallbacks:
    """Change detection and notification."""

    def test_callback_on_first_evaluation(self) -> None:
        engine = DegradationEngine()
        states: list[DegradationState] = []
        engine.on_change(lambda s: states.append(s))

        engine.evaluate()
        assert len(states) == 1  # First evaluation always notifies

    def test_callback_on_state_change(self) -> None:
        engine = DegradationEngine()
        states: list[DegradationState] = []
        engine.on_change(lambda s: states.append(s))

        engine.evaluate(network_ok=True)
        engine.evaluate(network_ok=False)  # Changed
        assert len(states) == 2

    def test_no_callback_on_same_state(self) -> None:
        engine = DegradationEngine()
        states: list[DegradationState] = []
        engine.on_change(lambda s: states.append(s))

        engine.evaluate(network_ok=True)
        engine.evaluate(network_ok=True)  # Same
        assert len(states) == 1  # No duplicate

    def test_callback_error_doesnt_crash(self) -> None:
        engine = DegradationEngine()

        def bad_callback(s: DegradationState) -> None:
            raise RuntimeError("callback error")

        engine.on_change(bad_callback)
        # Should not raise
        state = engine.evaluate()
        assert state is not None


class TestDegradationUserMessages:
    """User-facing message generation."""

    def test_no_messages_when_healthy(self) -> None:
        engine = DegradationEngine()
        state = engine.evaluate()
        assert state.user_messages == []

    def test_get_user_message_returns_first(self) -> None:
        engine = DegradationEngine()
        engine.evaluate(network_ok=False)
        msg = engine.get_user_message()
        assert msg is not None
        assert "local" in msg.lower()

    def test_get_user_message_none_when_healthy(self) -> None:
        engine = DegradationEngine()
        engine.evaluate()
        assert engine.get_user_message() is None

    def test_battery_critical_beats_low(self) -> None:
        """Critical message takes precedence over low battery."""
        engine = DegradationEngine(battery_low_pct=15.0, battery_critical_pct=5.0)
        state = engine.evaluate(battery_pct=3.0)
        # Only critical message, not both
        assert len(state.user_messages) == 1
        assert "critical" in state.user_messages[0].lower()


class TestDegradationThresholds:
    """Custom threshold configuration."""

    def test_custom_storage_threshold(self) -> None:
        engine = DegradationEngine(storage_full_pct=80.0)
        state = engine.evaluate(health={"storage": {"used_pct": 82.0}})
        assert state.storage_ok is False

    def test_custom_npu_thresholds(self) -> None:
        engine = DegradationEngine(npu_throttle_temp=60.0, npu_shutdown_temp=70.0)
        state = engine.evaluate(health={"npu": {"temp_c": 65.0}})
        assert state.llm_available is True  # Throttle only
        assert len(state.user_messages) == 1

    def test_missing_health_data_is_healthy(self) -> None:
        """No health data = assume healthy."""
        engine = DegradationEngine()
        state = engine.evaluate(health={})
        assert state.is_fully_operational is True

    def test_none_health_is_healthy(self) -> None:
        engine = DegradationEngine()
        state = engine.evaluate(health=None)
        assert state.is_fully_operational is True
