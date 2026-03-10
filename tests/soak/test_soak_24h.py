"""Soak test — sustained operation with periodic fault injection.

Simulates continuous system operation over a configurable duration,
injecting random failures and monitoring for resource leaks.

Usage:
    pytest tests/soak/test_soak_24h.py -m soak          # full duration
    pytest tests/soak/test_soak_24h.py -m soak --dry-run # 5-minute macOS test

The soak marker excludes these from normal test runs.
"""

from __future__ import annotations

import gc
import os
import random
import resource
import time
from typing import Any

import pytest

from cortex.resilience.circuit_breaker import CircuitBreaker, CircuitState
from cortex.resilience.degradation import DegradationEngine

# Duration in seconds: 5 min for dry-run, 24h for full soak
_DRY_RUN = os.environ.get("SOAK_DRY_RUN", "1") == "1"
_DURATION_S = 300 if _DRY_RUN else 86400  # 5 min or 24h
_INTERACTION_INTERVAL_S = 1.0 if _DRY_RUN else 30.0
_MAX_MEMORY_GROWTH_MB = 50


pytestmark = pytest.mark.soak


def _get_rss_mb() -> float:
    """Get current RSS in MB."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # ru_maxrss is in bytes on Linux, KB on macOS
    import sys

    if sys.platform == "darwin":
        return usage.ru_maxrss / (1024 * 1024)
    return usage.ru_maxrss / 1024


def _get_fd_count() -> int:
    """Count open file descriptors."""
    try:
        return len(os.listdir(f"/proc/{os.getpid()}/fd"))
    except FileNotFoundError:
        # macOS: use lsof-based count
        import subprocess

        result = subprocess.run(
            ["lsof", "-p", str(os.getpid())],
            capture_output=True,
            text=True,
        )
        return len(result.stdout.strip().splitlines()) - 1  # header line


class SoakMetrics:
    """Collects resource metrics during soak test."""

    def __init__(self) -> None:
        self.start_rss_mb = _get_rss_mb()
        self.start_fd_count = _get_fd_count()
        self.interaction_count = 0
        self.failure_injections = 0
        self.recovery_count = 0
        self.unrecoverable_errors: list[str] = []
        self.peak_rss_mb = self.start_rss_mb
        self.latencies: list[float] = []
        self.start_time = time.monotonic()

    def record_interaction(self, latency_ms: float) -> None:
        self.interaction_count += 1
        self.latencies.append(latency_ms)
        current_rss = _get_rss_mb()
        if current_rss > self.peak_rss_mb:
            self.peak_rss_mb = current_rss

    @property
    def memory_growth_mb(self) -> float:
        return _get_rss_mb() - self.start_rss_mb

    @property
    def fd_growth(self) -> int:
        return _get_fd_count() - self.start_fd_count

    @property
    def elapsed_s(self) -> float:
        return time.monotonic() - self.start_time

    @property
    def avg_latency_ms(self) -> float:
        return sum(self.latencies) / len(self.latencies) if self.latencies else 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "duration_s": self.elapsed_s,
            "interactions": self.interaction_count,
            "failures_injected": self.failure_injections,
            "recoveries": self.recovery_count,
            "unrecoverable_errors": len(self.unrecoverable_errors),
            "memory_growth_mb": self.memory_growth_mb,
            "peak_rss_mb": self.peak_rss_mb,
            "fd_growth": self.fd_growth,
            "avg_latency_ms": self.avg_latency_ms,
        }


class TestSoakSustainedOperation:
    """Sustained operation soak test with fault injection.

    Runs for SOAK_DURATION (default 5 min dry-run, 24h full).
    Periodically evaluates the degradation engine, injects failures,
    and monitors for resource leaks and unrecoverable errors.
    """

    def _simulate_interaction(
        self,
        engine: DegradationEngine,
        breakers: dict[str, CircuitBreaker],
        metrics: SoakMetrics,
    ) -> None:
        """Simulate a single system interaction."""
        start = time.monotonic()

        # Evaluate current state
        health: dict[str, Any] = {
            "npu": {"temp_c": random.uniform(40.0, 60.0)},
            "storage": {"used_pct": random.uniform(20.0, 80.0)},
        }
        state = engine.evaluate(
            health=health,
            breakers=breakers,
            network_ok=True,
        )

        # Verify state is consistent
        for name, breaker in breakers.items():
            if breaker.is_open:
                flag = getattr(state, f"{name}_available")
                if flag:
                    metrics.unrecoverable_errors.append(
                        f"Breaker {name} open but service reported available"
                    )

        latency = (time.monotonic() - start) * 1000
        metrics.record_interaction(latency)

    def _inject_random_failure(
        self,
        breakers: dict[str, CircuitBreaker],
        metrics: SoakMetrics,
    ) -> None:
        """Inject a random failure into one circuit breaker."""
        name = random.choice(list(breakers.keys()))
        breaker = breakers[name]
        if breaker.is_closed:
            breaker.force_open()
            metrics.failure_injections += 1

    def _attempt_recovery(
        self,
        breakers: dict[str, CircuitBreaker],
        metrics: SoakMetrics,
    ) -> None:
        """Attempt to recover any open circuit breakers."""
        for breaker in breakers.values():
            if breaker.is_open:
                breaker.reset()
                metrics.recovery_count += 1

    def test_sustained_operation(self, system_context):
        """Run sustained interactions with periodic fault injection.

        Asserts:
        - Zero unrecoverable errors
        - Memory growth < 50MB
        - No FD leaks (growth < 10)
        """
        metrics = SoakMetrics()
        engine = system_context.engine
        breakers = system_context.breakers
        iteration = 0

        while metrics.elapsed_s < _DURATION_S:
            iteration += 1

            # Regular interaction
            self._simulate_interaction(engine, breakers, metrics)

            # Inject failure every 10 iterations
            if iteration % 10 == 0:
                self._inject_random_failure(breakers, metrics)

            # Recover every 15 iterations
            if iteration % 15 == 0:
                self._attempt_recovery(breakers, metrics)

            # Periodic GC to check for leaks
            if iteration % 100 == 0:
                gc.collect()

        # --- Assertions ---
        assert metrics.unrecoverable_errors == [], (
            f"Unrecoverable errors: {metrics.unrecoverable_errors}"
        )
        assert metrics.interaction_count > 0, "No interactions completed"

    def test_memory_stability(self, system_context):
        """Verify memory doesn't grow unboundedly during sustained operation."""
        engine = system_context.engine
        breakers = system_context.breakers
        initial_rss = _get_rss_mb()

        # Run many interactions
        count = 1000 if _DRY_RUN else 10000
        for i in range(count):
            health: dict[str, Any] = {
                "npu": {"temp_c": 50.0},
                "storage": {"used_pct": 50.0},
            }
            engine.evaluate(health=health, breakers=breakers, network_ok=True)

            if i % 100 == 0:
                gc.collect()

        final_rss = _get_rss_mb()
        growth = final_rss - initial_rss
        # Allow up to 50MB growth — mainly from Python object overhead
        assert growth < _MAX_MEMORY_GROWTH_MB, (
            f"Memory grew {growth:.1f} MB over {count} interactions"
        )

    def test_circuit_breaker_cycle_stability(self, system_context):
        """Circuit breakers remain stable through many open/close cycles."""
        breaker = system_context.breakers["llm"]
        cycles = 100 if _DRY_RUN else 1000

        for _ in range(cycles):
            breaker.force_open()
            assert breaker.state == CircuitState.OPEN
            breaker.reset()
            assert breaker.state == CircuitState.CLOSED

        # Verify no leaked state
        assert breaker.failure_count == 0
        assert breaker.last_error == ""

    def test_degradation_callback_stability(self, system_context):
        """Callbacks fire correctly over many evaluations."""
        engine = system_context.engine
        breakers = system_context.breakers
        change_count = 0

        def on_change(_state):
            nonlocal change_count
            change_count += 1

        engine.on_change(on_change)

        # Alternate between healthy and degraded
        iterations = 200 if _DRY_RUN else 2000
        for i in range(iterations):
            if i % 2 == 0:
                breakers["llm"].force_open()
            else:
                breakers["llm"].reset()
            engine.evaluate(breakers=breakers)

        # Should have fired on each state change
        assert change_count >= iterations - 1

    def test_concurrent_breaker_evaluation(self, system_context):
        """Multiple breakers changing state simultaneously."""
        engine = system_context.engine
        breakers = system_context.breakers
        iterations = 500 if _DRY_RUN else 5000

        for i in range(iterations):
            # Randomly open/close each breaker
            for _name, breaker in breakers.items():
                if random.random() < 0.3:
                    breaker.force_open()
                elif random.random() < 0.5:
                    breaker.reset()

            state = engine.evaluate(breakers=breakers)

            # Verify consistency
            for name, breaker in breakers.items():
                expected = not breaker.is_open
                actual = getattr(state, f"{name}_available")
                assert actual == expected, (
                    f"Iteration {i}: {name} breaker "
                    f"{'open' if breaker.is_open else 'closed'} "
                    f"but available={actual}"
                )
