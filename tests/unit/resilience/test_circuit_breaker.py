"""Tests for circuit breaker — state machine, recovery, concurrent calls."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest

from cortex.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)


class TestCircuitBreakerInit:
    """Initial state and configuration."""

    def test_initial_state_is_closed(self) -> None:
        cb = CircuitBreaker("test")
        assert cb.state == CircuitState.CLOSED
        assert cb.is_closed is True
        assert cb.is_open is False

    def test_initial_failure_count_zero(self) -> None:
        cb = CircuitBreaker("test")
        assert cb.failure_count == 0

    def test_name_property(self) -> None:
        cb = CircuitBreaker("llm")
        assert cb.name == "llm"

    def test_initial_last_error_empty(self) -> None:
        cb = CircuitBreaker("test")
        assert cb.last_error == ""

    def test_initial_transitions_empty(self) -> None:
        cb = CircuitBreaker("test")
        assert cb.transitions == []


class TestCircuitBreakerStateTransitions:
    """CLOSED → OPEN → HALF_OPEN → CLOSED transitions."""

    def test_stays_closed_under_threshold(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure("err1")
        cb.record_failure("err2")
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 2

    def test_opens_at_threshold(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure("err1")
        cb.record_failure("err2")
        cb.record_failure("err3")
        assert cb.state == CircuitState.OPEN
        assert cb.is_open is True

    def test_success_resets_failure_count(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure("err1")
        cb.record_failure("err2")
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED

    def test_open_transitions_to_half_open_after_recovery(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_s=0.0)
        cb.record_failure("err")
        assert cb._state == CircuitState.OPEN
        # Accessing .state triggers auto-transition when timeout elapsed
        assert cb.state == CircuitState.HALF_OPEN

    def test_open_stays_open_before_recovery(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_s=9999.0)
        cb.record_failure("err")
        assert cb.state == CircuitState.OPEN

    def test_half_open_success_closes(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_s=0.0)
        cb.record_failure("err")
        _ = cb.state  # Trigger OPEN → HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_s=9999.0)
        cb.record_failure("err")
        # Manually transition to HALF_OPEN
        cb._transition(CircuitState.HALF_OPEN, "manual test")
        cb.record_failure("probe fail")
        assert cb._state == CircuitState.OPEN

    def test_transitions_are_recorded(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_s=0.0)
        cb.record_failure("err")  # CLOSED → OPEN
        _ = cb.state  # OPEN → HALF_OPEN
        cb.record_success()  # HALF_OPEN → CLOSED
        transitions = cb.transitions
        assert len(transitions) == 3
        assert transitions[0].from_state == CircuitState.CLOSED
        assert transitions[0].to_state == CircuitState.OPEN
        assert transitions[1].to_state == CircuitState.HALF_OPEN
        assert transitions[2].to_state == CircuitState.CLOSED


class TestCircuitBreakerCall:
    """Async call() wrapper."""

    @pytest.mark.asyncio()
    async def test_call_success_flows_through(self) -> None:
        cb = CircuitBreaker("test")
        func = AsyncMock(return_value=42)
        result = await cb.call(func, "a", b="c")
        assert result == 42
        func.assert_called_once_with("a", b="c")

    @pytest.mark.asyncio()
    async def test_call_failure_records_and_reraises(self) -> None:
        cb = CircuitBreaker("test")
        func = AsyncMock(side_effect=RuntimeError("boom"))
        with pytest.raises(RuntimeError, match="boom"):
            await cb.call(func)
        assert cb.failure_count == 1
        assert "boom" in cb.last_error

    @pytest.mark.asyncio()
    async def test_call_rejected_when_open(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_s=9999.0)
        cb.record_failure("err")
        func = AsyncMock(return_value=42)
        with pytest.raises(CircuitOpenError):
            await cb.call(func)
        func.assert_not_called()

    @pytest.mark.asyncio()
    async def test_call_allowed_in_half_open(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_s=0.0)
        cb.record_failure("err")
        _ = cb.state  # OPEN → HALF_OPEN
        func = AsyncMock(return_value="ok")
        result = await cb.call(func)
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio()
    async def test_half_open_probe_limit(self) -> None:
        cb = CircuitBreaker(
            "test", failure_threshold=1, recovery_timeout_s=0.0, half_open_max_calls=1,
        )
        cb.record_failure("err")
        _ = cb.state  # OPEN → HALF_OPEN
        # First call allowed
        cb._half_open_calls = 1  # Simulate probe already in flight
        func = AsyncMock(return_value="ok")
        with pytest.raises(CircuitOpenError, match="probe limit"):
            await cb.call(func)

    @pytest.mark.asyncio()
    async def test_call_failure_in_half_open_reopens(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_s=9999.0)
        cb.record_failure("err")
        # Manually transition to HALF_OPEN for testing
        cb._transition(CircuitState.HALF_OPEN, "manual test")
        cb._half_open_calls = 0
        func = AsyncMock(side_effect=RuntimeError("still broken"))
        with pytest.raises(RuntimeError):
            await cb.call(func)
        assert cb._state == CircuitState.OPEN

    @pytest.mark.asyncio()
    async def test_consecutive_failures_needed(self) -> None:
        """Interleaved success prevents opening."""
        cb = CircuitBreaker("test", failure_threshold=3)
        fail = AsyncMock(side_effect=RuntimeError("err"))
        ok = AsyncMock(return_value="ok")
        with pytest.raises(RuntimeError):
            await cb.call(fail)
        with pytest.raises(RuntimeError):
            await cb.call(fail)
        await cb.call(ok)  # Resets count
        with pytest.raises(RuntimeError):
            await cb.call(fail)
        assert cb.state == CircuitState.CLOSED  # Only 1 failure after reset


class TestCircuitBreakerForceAndReset:
    """Manual control methods."""

    def test_force_open(self) -> None:
        cb = CircuitBreaker("test")
        cb.force_open()
        assert cb.is_open is True

    def test_force_open_when_already_open(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1)
        cb.record_failure("err")
        transitions_before = len(cb.transitions)
        cb.force_open()  # No additional transition since already open
        assert len(cb.transitions) == transitions_before

    def test_reset_from_open(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1)
        cb.record_failure("err")
        assert cb.is_open is True
        cb.reset()
        assert cb.is_closed is True
        assert cb.failure_count == 0
        assert cb.last_error == ""

    def test_reset_from_closed_no_transition(self) -> None:
        cb = CircuitBreaker("test")
        transitions_before = len(cb.transitions)
        cb.reset()
        # No transition recorded when already closed
        assert len(cb.transitions) == transitions_before


class TestCircuitBreakerSerialization:
    """to_dict() output."""

    def test_to_dict_closed(self) -> None:
        cb = CircuitBreaker("llm")
        d = cb.to_dict()
        assert d["name"] == "llm"
        assert d["state"] == "closed"
        assert d["failure_count"] == 0
        assert d["last_error"] == ""
        assert d["transition_count"] == 0

    def test_to_dict_open(self) -> None:
        cb = CircuitBreaker("tts", failure_threshold=1, recovery_timeout_s=9999.0)
        cb.record_failure("timeout")
        d = cb.to_dict()
        assert d["state"] == "open"
        assert d["failure_count"] == 1
        assert d["last_error"] == "timeout"
        assert d["transition_count"] == 1


class TestCircuitBreakerRecoveryTimeout:
    """Time-based recovery behavior."""

    def test_recovery_timeout_with_monkeypatch(self) -> None:
        """Use time patching to test recovery without real delays."""
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_s=30.0)
        cb.record_failure("err")
        assert cb._state == CircuitState.OPEN

        # Fake the failure time to 31 seconds ago
        cb._last_failure_time = time.monotonic() - 31.0
        assert cb.state == CircuitState.HALF_OPEN

    def test_no_recovery_before_timeout(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_s=30.0)
        cb.record_failure("err")
        # Failure just happened — should stay open
        assert cb.state == CircuitState.OPEN
