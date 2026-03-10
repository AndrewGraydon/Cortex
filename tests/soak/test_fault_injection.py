"""Fault injection tests — validates all 8 DD-033 graceful degradation scenarios.

Each test injects a specific failure condition and verifies the system
produces the correct DegradationState per the DD-033 matrix.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from cortex.hal.npu.mock import MockError
from cortex.resilience.circuit_breaker import CircuitOpenError, CircuitState

# ---------------------------------------------------------------------------
# DD-033 Scenario 1: All LLM providers fail → regex-only fallback
# ---------------------------------------------------------------------------


class TestLlmFailRegexFallback:
    """When LLM circuit opens, system falls back to regex-only responses."""

    def test_llm_breaker_open_disables_llm(self, system_context):
        system_context.breakers["llm"].force_open()
        state = system_context.evaluate()
        assert state.llm_available is False
        assert state.tts_available is True
        assert state.asr_available is True

    def test_llm_fail_user_message(self, system_context):
        system_context.breakers["llm"].force_open()
        state = system_context.evaluate()
        assert any("timers" in m for m in state.user_messages)

    def test_llm_breaker_opens_after_failures(self, system_context):
        breaker = system_context.breakers["llm"]
        for _ in range(3):
            breaker.record_failure("provider timeout")
        assert breaker.state == CircuitState.OPEN
        state = system_context.evaluate()
        assert state.llm_available is False

    def test_llm_tts_asr_independent(self, system_context):
        """TTS and ASR remain available when LLM fails."""
        system_context.breakers["llm"].force_open()
        state = system_context.evaluate()
        assert state.tts_available is True
        assert state.asr_available is True
        assert not state.is_fully_operational

    async def test_llm_circuit_rejects_calls(self, system_context):
        """Open LLM circuit raises CircuitOpenError on call."""
        system_context.breakers["llm"].force_open()
        with pytest.raises(CircuitOpenError):
            await system_context.breakers["llm"].call(asyncio.sleep, 0)


# ---------------------------------------------------------------------------
# DD-033 Scenario 2: TTS fails → response on LCD
# ---------------------------------------------------------------------------


class TestTtsFailLcdFallback:
    """When TTS fails, responses are displayed on LCD instead of spoken."""

    def test_tts_breaker_open_disables_tts(self, system_context):
        system_context.breakers["tts"].force_open()
        state = system_context.evaluate()
        assert state.tts_available is False
        assert state.llm_available is True

    def test_tts_fail_user_message(self, system_context):
        system_context.breakers["tts"].force_open()
        state = system_context.evaluate()
        assert any("screen" in m for m in state.user_messages)

    def test_tts_failure_progression(self, system_context):
        breaker = system_context.breakers["tts"]
        assert breaker.is_closed
        breaker.record_failure("inference error")
        breaker.record_failure("inference error")
        assert breaker.is_closed
        breaker.record_failure("inference error")
        assert breaker.is_open


# ---------------------------------------------------------------------------
# DD-033 Scenario 3: ASR fails → "Voice unavailable — use web UI"
# ---------------------------------------------------------------------------


class TestAsrFailWebUiMessage:
    """When ASR fails, user is directed to web UI."""

    def test_asr_breaker_open_disables_asr(self, system_context):
        system_context.breakers["asr"].force_open()
        state = system_context.evaluate()
        assert state.asr_available is False
        assert state.llm_available is True
        assert state.tts_available is True

    def test_asr_fail_user_message(self, system_context):
        system_context.breakers["asr"].force_open()
        state = system_context.evaluate()
        assert any("web UI" in m for m in state.user_messages)

    async def test_asr_error_injection(self, system_context):
        """Mock NPU error injection triggers breaker failures."""
        system_context.npu.inject_error(
            MockError("sensevoice", "inference_error", "ASR decode failure")
        )
        breaker = system_context.breakers["asr"]
        for _ in range(3):
            with contextlib.suppress(Exception):
                await breaker.call(
                    system_context.npu.infer,
                    system_context.npu._loaded_models["sensevoice"],
                    None,
                )
        state = system_context.evaluate()
        assert state.asr_available is False


# ---------------------------------------------------------------------------
# DD-033 Scenario 4: Network down → transparent for local ops
# ---------------------------------------------------------------------------


class TestNetworkDownLocalContinues:
    """When network is down, local operations continue."""

    def test_network_down(self, system_context):
        state = system_context.evaluate(network_ok=False)
        assert state.network_available is False
        assert state.llm_available is True
        assert state.tts_available is True
        assert state.asr_available is True

    def test_network_down_user_message(self, system_context):
        state = system_context.evaluate(network_ok=False)
        assert any("local-only" in m for m in state.user_messages)

    def test_network_up_no_message(self, system_context):
        state = system_context.evaluate(network_ok=True)
        assert state.network_available is True
        assert not any("Network" in m for m in state.user_messages)

    def test_network_recovery(self, system_context):
        """Network down then up restores full operation."""
        state = system_context.evaluate(network_ok=False)
        assert not state.network_available
        state = system_context.evaluate(network_ok=True)
        assert state.network_available


# ---------------------------------------------------------------------------
# DD-033 Scenario 5: Battery < 15% → reduce brightness, suspend polling
# ---------------------------------------------------------------------------


class TestBatteryLowBrightnessReduced:
    """Low battery triggers power-saving measures."""

    def test_battery_low(self, system_context):
        state = system_context.evaluate(battery_pct=10.0)
        assert state.power_ok is False

    def test_battery_low_user_message(self, system_context):
        state = system_context.evaluate(battery_pct=10.0)
        assert any("low" in m.lower() for m in state.user_messages)

    def test_battery_at_threshold(self, system_context):
        state = system_context.evaluate(battery_pct=15.0)
        assert state.power_ok is False

    def test_battery_above_threshold(self, system_context):
        state = system_context.evaluate(battery_pct=16.0)
        assert state.power_ok is True


# ---------------------------------------------------------------------------
# DD-033 Scenario 6: Battery < 5% → clean shutdown
# ---------------------------------------------------------------------------


class TestBatteryCriticalCleanShutdown:
    """Critical battery triggers clean shutdown sequence."""

    def test_battery_critical(self, system_context):
        state = system_context.evaluate(battery_pct=3.0)
        assert state.power_ok is False

    def test_battery_critical_user_message(self, system_context):
        state = system_context.evaluate(battery_pct=3.0)
        assert any("shutting down" in m.lower() for m in state.user_messages)

    def test_battery_zero(self, system_context):
        state = system_context.evaluate(battery_pct=0.0)
        assert state.power_ok is False
        assert any("shutting down" in m.lower() for m in state.user_messages)

    def test_mains_power_no_battery_concern(self, system_context):
        """None battery_pct means mains power — no concern."""
        state = system_context.evaluate(battery_pct=None)
        assert state.power_ok is True


# ---------------------------------------------------------------------------
# DD-033 Scenario 7: Storage full → disable audit writes
# ---------------------------------------------------------------------------


class TestStorageFullDisableAudit:
    """Storage full triggers audit write suspension."""

    def test_storage_full(self, system_context):
        state = system_context.evaluate(
            health={"storage": {"used_pct": 98.0}},
        )
        assert state.storage_ok is False

    def test_storage_full_user_message(self, system_context):
        state = system_context.evaluate(
            health={"storage": {"used_pct": 98.0}},
        )
        assert any("storage" in m.lower() for m in state.user_messages)

    def test_storage_at_threshold(self, system_context):
        state = system_context.evaluate(
            health={"storage": {"used_pct": 95.0}},
        )
        assert state.storage_ok is False

    def test_storage_below_threshold(self, system_context):
        state = system_context.evaluate(
            health={"storage": {"used_pct": 94.0}},
        )
        assert state.storage_ok is True


# ---------------------------------------------------------------------------
# DD-033 Scenario 8: Service crash → brief interruption, state recovery
# ---------------------------------------------------------------------------


class TestServiceCrashRecovery:
    """Service crash and restart recovers from saved state."""

    def test_breaker_state_persists_across_evaluation(self, system_context):
        """Circuit breaker state is preserved across evaluations."""
        system_context.breakers["llm"].force_open()
        state1 = system_context.evaluate()
        state2 = system_context.evaluate()
        assert state1.llm_available is False
        assert state2.llm_available is False

    def test_breaker_reset_restores_service(self, system_context):
        """Resetting breaker after crash simulates successful restart."""
        system_context.breakers["llm"].force_open()
        state = system_context.evaluate()
        assert state.llm_available is False
        system_context.breakers["llm"].reset()
        state = system_context.evaluate()
        assert state.llm_available is True

    def test_engine_tracks_state_changes(self, system_context):
        """Degradation engine callback fires on state change."""
        system_context.breakers["llm"].force_open()
        system_context.evaluate()
        assert len(system_context.state_changes) == 1
        assert system_context.state_changes[0].llm_available is False


# ---------------------------------------------------------------------------
# NPU thermal scenarios (DD-033 extensions)
# ---------------------------------------------------------------------------


class TestNpuOverheat:
    """NPU temperature-based degradation."""

    def test_npu_throttle_warning(self, system_context):
        """NPU at 80°C triggers throttle warning but services remain."""
        state = system_context.evaluate(
            health={"npu": {"temp_c": 80.0}},
        )
        assert state.llm_available is True
        assert state.tts_available is True
        assert any("cool down" in m.lower() for m in state.user_messages)

    def test_npu_shutdown_disables_all(self, system_context):
        """NPU at 90°C disables all NPU services."""
        state = system_context.evaluate(
            health={"npu": {"temp_c": 90.0}},
        )
        assert state.llm_available is False
        assert state.tts_available is False
        assert state.asr_available is False

    def test_npu_normal_temp(self, system_context):
        """NPU at normal temp — no messages."""
        state = system_context.evaluate(
            health={"npu": {"temp_c": 50.0}},
        )
        assert state.llm_available is True
        assert not state.user_messages

    def test_npu_at_throttle_boundary(self, system_context):
        state = system_context.evaluate(
            health={"npu": {"temp_c": 75.0}},
        )
        assert any("cool down" in m.lower() for m in state.user_messages)

    def test_npu_at_shutdown_boundary(self, system_context):
        state = system_context.evaluate(
            health={"npu": {"temp_c": 85.0}},
        )
        assert state.llm_available is False


# ---------------------------------------------------------------------------
# Compound failures — multiple simultaneous issues
# ---------------------------------------------------------------------------


class TestCompoundFailures:
    """Multiple simultaneous failures degrade gracefully."""

    def test_llm_and_tts_fail(self, system_context):
        """LLM + TTS both fail → regex + LCD text."""
        system_context.breakers["llm"].force_open()
        system_context.breakers["tts"].force_open()
        state = system_context.evaluate()
        assert state.llm_available is False
        assert state.tts_available is False
        assert state.asr_available is True
        assert len(state.user_messages) == 2

    def test_all_services_fail(self, system_context):
        """All three NPU services fail."""
        for name in ("llm", "tts", "asr"):
            system_context.breakers[name].force_open()
        state = system_context.evaluate()
        assert not state.llm_available
        assert not state.tts_available
        assert not state.asr_available
        assert len(state.user_messages) == 3

    def test_npu_overheat_plus_network_down(self, system_context):
        """NPU overheat + network down — compound degradation."""
        state = system_context.evaluate(
            health={"npu": {"temp_c": 90.0}},
            network_ok=False,
        )
        assert not state.llm_available
        assert not state.network_available
        assert len(state.user_messages) >= 2

    def test_storage_full_plus_battery_low(self, system_context):
        state = system_context.evaluate(
            health={"storage": {"used_pct": 98.0}},
            battery_pct=10.0,
        )
        assert not state.storage_ok
        assert not state.power_ok
        assert len(state.user_messages) == 2

    def test_everything_failing(self, system_context):
        """Worst case: all services, network, storage, battery, NPU heat."""
        for name in ("llm", "tts", "asr"):
            system_context.breakers[name].force_open()
        state = system_context.evaluate(
            health={
                "npu": {"temp_c": 90.0},
                "storage": {"used_pct": 99.0},
            },
            battery_pct=2.0,
            network_ok=False,
        )
        assert not state.is_fully_operational
        # Should have messages for each failure category
        assert len(state.user_messages) >= 5


# ---------------------------------------------------------------------------
# Recovery scenarios
# ---------------------------------------------------------------------------


class TestRecoveryAfterRestore:
    """System recovers to full operation after failures are resolved."""

    def test_llm_recovery(self, system_context):
        system_context.breakers["llm"].force_open()
        state = system_context.evaluate()
        assert not state.llm_available
        system_context.breakers["llm"].reset()
        state = system_context.evaluate()
        assert state.llm_available

    async def test_breaker_half_open_recovery(self, system_context):
        """Breaker recovers through HALF_OPEN → CLOSED."""
        breaker = system_context.breakers["llm"]
        breaker.force_open()
        # Wait for recovery timeout
        await asyncio.sleep(0.6)
        assert breaker.state == CircuitState.HALF_OPEN
        # Successful probe
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED
        state = system_context.evaluate()
        assert state.llm_available is True

    def test_full_recovery_from_compound(self, system_context):
        """All services recover after compound failure."""
        for name in ("llm", "tts", "asr"):
            system_context.breakers[name].force_open()
        state = system_context.evaluate(network_ok=False)
        assert not state.is_fully_operational

        for name in ("llm", "tts", "asr"):
            system_context.breakers[name].reset()
        state = system_context.evaluate(network_ok=True)
        assert state.is_fully_operational

    def test_state_change_callbacks_on_recovery(self, system_context):
        """Callbacks fire both on degradation and recovery."""
        system_context.breakers["tts"].force_open()
        system_context.evaluate()
        system_context.breakers["tts"].reset()
        system_context.evaluate()
        # Should have at least 2 state changes (degrade + recover)
        assert len(system_context.state_changes) >= 2

    def test_transition_history_recorded(self, system_context):
        breaker = system_context.breakers["llm"]
        breaker.force_open()
        breaker.reset()
        transitions = breaker.transitions
        assert len(transitions) == 2
        assert transitions[0].to_state == CircuitState.OPEN
        assert transitions[1].to_state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# Circuit breaker integration details
# ---------------------------------------------------------------------------


class TestCircuitBreakerIntegration:
    """Circuit breaker behavior under fault injection."""

    async def test_concurrent_failures(self, system_context):
        """Multiple concurrent failures correctly tracked."""
        breaker = system_context.breakers["llm"]

        async def failing_func():
            msg = "timeout"
            raise TimeoutError(msg)

        for _ in range(3):
            with pytest.raises(TimeoutError):
                await breaker.call(failing_func)
        assert breaker.is_open

    async def test_mixed_success_failure(self, system_context):
        """Successes reset failure count."""
        breaker = system_context.breakers["tts"]

        async def succeed():
            return "ok"

        breaker.record_failure("err")
        breaker.record_failure("err")
        await breaker.call(succeed)  # success resets count
        breaker.record_failure("err")
        breaker.record_failure("err")
        assert breaker.is_closed  # Still closed, count was reset

    def test_breaker_serialization(self, system_context):
        breaker = system_context.breakers["asr"]
        breaker.force_open()
        data = breaker.to_dict()
        assert data["name"] == "asr"
        assert data["state"] == "open"
        assert data["transition_count"] == 1

    def test_independent_breakers(self, system_context):
        """Breakers track failures independently."""
        system_context.breakers["llm"].force_open()
        assert system_context.breakers["tts"].is_closed
        assert system_context.breakers["asr"].is_closed
