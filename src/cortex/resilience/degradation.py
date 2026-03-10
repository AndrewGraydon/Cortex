"""Degradation engine — evaluates DD-033 failure scenarios and produces system state.

Reactive engine: receives health updates and circuit breaker state changes,
evaluates the graceful degradation matrix, and produces a DegradationState
describing what's available and user-facing messages.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from cortex.resilience.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


@dataclass
class DegradationState:
    """Current system degradation status.

    Each flag indicates whether a capability is available.
    User messages are generated for any degraded capabilities.
    """

    llm_available: bool = True
    tts_available: bool = True
    asr_available: bool = True
    network_available: bool = True
    storage_ok: bool = True
    power_ok: bool = True
    user_messages: list[str] = field(default_factory=list)

    @property
    def is_fully_operational(self) -> bool:
        return all([
            self.llm_available,
            self.tts_available,
            self.asr_available,
            self.network_available,
            self.storage_ok,
            self.power_ok,
        ])


# DD-033 user-facing messages for each failure scenario
_DEGRADATION_MESSAGES = {
    "llm_fail": (
        "I can't think right now, but I can still set timers and tell you the time."
    ),
    "tts_fail": "Voice output is unavailable. Responses will be shown on screen.",
    "asr_fail": "Voice input is unavailable — please use the web UI.",
    "network_down": "Network is unavailable. Running in local-only mode.",
    "battery_low": "Battery is getting low.",
    "battery_critical": "Battery critical. Saving state and shutting down.",
    "storage_full": "I'm running out of storage space.",
    "npu_throttle": "I need to cool down for a moment.",
    "npu_shutdown": "Something's too hot. Give me a minute to cool down.",
}


class DegradationEngine:
    """Evaluates system health and circuit breaker state to produce degradation state.

    Does not poll — call `evaluate()` when health or breaker state changes.
    The engine is stateless except for tracking the last emitted state.
    """

    def __init__(
        self,
        npu_throttle_temp: float = 75.0,
        npu_shutdown_temp: float = 85.0,
        storage_full_pct: float = 95.0,
        battery_low_pct: float = 15.0,
        battery_critical_pct: float = 5.0,
    ) -> None:
        self._npu_throttle_temp = npu_throttle_temp
        self._npu_shutdown_temp = npu_shutdown_temp
        self._storage_full_pct = storage_full_pct
        self._battery_low_pct = battery_low_pct
        self._battery_critical_pct = battery_critical_pct
        self._last_state: DegradationState | None = None
        self._on_change_callbacks: list[Any] = []

    @property
    def last_state(self) -> DegradationState | None:
        return self._last_state

    def on_change(self, callback: Any) -> None:
        """Register a callback for state changes."""
        self._on_change_callbacks.append(callback)

    def evaluate(
        self,
        health: dict[str, Any] | None = None,
        breakers: dict[str, CircuitBreaker] | None = None,
        battery_pct: float | None = None,
        network_ok: bool = True,
    ) -> DegradationState:
        """Evaluate the DD-033 degradation matrix.

        Args:
            health: System health dict with component details.
            breakers: Named circuit breakers (e.g. {"llm": breaker, "tts": ...}).
            battery_pct: Battery percentage (None = mains power).
            network_ok: Whether network connectivity is available.
        """
        state = DegradationState()
        health = health or {}
        breakers = breakers or {}

        # --- Circuit breaker checks ---
        llm_breaker = breakers.get("llm")
        if llm_breaker and llm_breaker.is_open:
            state.llm_available = False
            state.user_messages.append(_DEGRADATION_MESSAGES["llm_fail"])

        tts_breaker = breakers.get("tts")
        if tts_breaker and tts_breaker.is_open:
            state.tts_available = False
            state.user_messages.append(_DEGRADATION_MESSAGES["tts_fail"])

        asr_breaker = breakers.get("asr")
        if asr_breaker and asr_breaker.is_open:
            state.asr_available = False
            state.user_messages.append(_DEGRADATION_MESSAGES["asr_fail"])

        # --- Network ---
        if not network_ok:
            state.network_available = False
            state.user_messages.append(_DEGRADATION_MESSAGES["network_down"])

        # --- Storage ---
        storage = health.get("storage", {})
        storage_pct = storage.get("used_pct", 0.0)
        if storage_pct >= self._storage_full_pct:
            state.storage_ok = False
            state.user_messages.append(_DEGRADATION_MESSAGES["storage_full"])

        # --- Battery ---
        if battery_pct is not None:
            if battery_pct <= self._battery_critical_pct:
                state.power_ok = False
                state.user_messages.append(_DEGRADATION_MESSAGES["battery_critical"])
            elif battery_pct <= self._battery_low_pct:
                state.power_ok = False
                state.user_messages.append(_DEGRADATION_MESSAGES["battery_low"])

        # --- NPU thermal ---
        npu = health.get("npu", {})
        npu_temp = npu.get("temp_c", 0.0)
        if npu_temp >= self._npu_shutdown_temp:
            state.llm_available = False
            state.tts_available = False
            state.asr_available = False
            state.user_messages.append(_DEGRADATION_MESSAGES["npu_shutdown"])
        elif npu_temp >= self._npu_throttle_temp:
            state.user_messages.append(_DEGRADATION_MESSAGES["npu_throttle"])

        # --- Notify on change ---
        if self._last_state is None or self._state_changed(self._last_state, state):
            self._last_state = state
            for cb in self._on_change_callbacks:
                try:
                    cb(state)
                except Exception:
                    logger.exception("Degradation callback error")

        self._last_state = state
        return state

    @staticmethod
    def _state_changed(old: DegradationState, new: DegradationState) -> bool:
        """Check if degradation state changed in any meaningful way."""
        return (
            old.llm_available != new.llm_available
            or old.tts_available != new.tts_available
            or old.asr_available != new.asr_available
            or old.network_available != new.network_available
            or old.storage_ok != new.storage_ok
            or old.power_ok != new.power_ok
        )

    def get_user_message(self) -> str | None:
        """Get the most important user-facing degradation message, or None."""
        if self._last_state and self._last_state.user_messages:
            return self._last_state.user_messages[0]
        return None
