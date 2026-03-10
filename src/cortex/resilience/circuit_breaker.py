"""Circuit breaker — prevents cascading failures by tracking error rates.

Three-state machine: CLOSED (normal) → OPEN (failing, reject fast) → HALF_OPEN (testing recovery).
Each inference call site (LLM, TTS, ASR) gets its own breaker instance.
"""

from __future__ import annotations

import enum
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(enum.Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal — calls flow through
    OPEN = "open"  # Failing — reject immediately
    HALF_OPEN = "half_open"  # Testing — allow one call to probe recovery


@dataclass
class CircuitTransition:
    """Record of a state transition."""

    from_state: CircuitState
    to_state: CircuitState
    timestamp: float
    reason: str


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit is open."""


class CircuitBreaker:
    """Tracks failures and short-circuits calls when a threshold is exceeded.

    Args:
        name: Identifier for this breaker (e.g. "llm", "tts", "asr").
        failure_threshold: Consecutive failures before opening.
        recovery_timeout_s: Seconds to wait before attempting recovery.
        half_open_max_calls: Calls allowed in half-open state to test recovery.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout_s: float = 30.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self._name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout_s = recovery_timeout_s
        self._half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time = 0.0
        self._last_error: str = ""
        self._transitions: list[CircuitTransition] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> CircuitState:
        # Auto-transition from OPEN → HALF_OPEN after recovery timeout
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self._recovery_timeout_s:
                self._transition(CircuitState.HALF_OPEN, "recovery timeout elapsed")
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def transitions(self) -> list[CircuitTransition]:
        return list(self._transitions)

    @property
    def is_closed(self) -> bool:
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    async def call(self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        """Execute a function through the circuit breaker.

        Raises CircuitOpenError if the circuit is open and recovery timeout
        has not elapsed.
        """
        current = self.state  # May trigger OPEN → HALF_OPEN transition

        if current == CircuitState.OPEN:
            raise CircuitOpenError(
                f"Circuit '{self._name}' is open (last error: {self._last_error})"
            )

        if current == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self._half_open_max_calls:
                raise CircuitOpenError(
                    f"Circuit '{self._name}' half-open probe limit reached"
                )
            self._half_open_calls += 1

        try:
            result = await func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as exc:
            self.record_failure(str(exc))
            raise

    def record_success(self) -> None:
        """Record a successful call."""
        self._success_count += 1

        if self._state == CircuitState.HALF_OPEN:
            self._transition(CircuitState.CLOSED, "probe succeeded")
            self._failure_count = 0
            self._half_open_calls = 0
            logger.info("Circuit '%s' recovered (closed)", self._name)
        elif self._state == CircuitState.CLOSED:
            # Reset failure count on success in closed state
            self._failure_count = 0

    def record_failure(self, error: str = "") -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        self._last_error = error

        if self._state == CircuitState.HALF_OPEN:
            self._transition(CircuitState.OPEN, f"probe failed: {error}")
            self._half_open_calls = 0
            logger.warning("Circuit '%s' probe failed, reopening", self._name)
        elif (
            self._state == CircuitState.CLOSED
            and self._failure_count >= self._failure_threshold
        ):
            self._transition(CircuitState.OPEN, f"threshold reached: {error}")
            logger.warning(
                "Circuit '%s' opened after %d failures",
                self._name,
                self._failure_count,
            )

    def reset(self) -> None:
        """Force reset to closed state."""
        if self._state != CircuitState.CLOSED:
            self._transition(CircuitState.CLOSED, "manual reset")
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_error = ""

    def force_open(self) -> None:
        """Force the circuit open (for testing/manual intervention)."""
        if self._state != CircuitState.OPEN:
            self._transition(CircuitState.OPEN, "forced open")
            self._last_failure_time = time.monotonic()

    def _transition(self, to_state: CircuitState, reason: str) -> None:
        """Record a state transition."""
        transition = CircuitTransition(
            from_state=self._state,
            to_state=to_state,
            timestamp=time.monotonic(),
            reason=reason,
        )
        self._transitions.append(transition)
        self._state = to_state

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for health/status endpoints."""
        return {
            "name": self._name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "last_error": self._last_error,
            "transition_count": len(self._transitions),
        }
