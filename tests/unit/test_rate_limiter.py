"""Tests for rate limiter — sliding window, per-IP tracking, reset."""

from __future__ import annotations

import time

from cortex.security.rate_limiter import RateLimiter


class TestRateLimiterBasic:
    """Basic rate limiting behavior."""

    def test_allows_under_limit(self) -> None:
        rl = RateLimiter(max_attempts=3, window_seconds=60.0)
        result = rl.check("1.2.3.4")
        assert result.allowed is True
        assert result.remaining == 3

    def test_records_and_decrements(self) -> None:
        rl = RateLimiter(max_attempts=3, window_seconds=60.0)
        r1 = rl.record("1.2.3.4")
        assert r1.remaining == 2
        r2 = rl.record("1.2.3.4")
        assert r2.remaining == 1

    def test_blocks_at_limit(self) -> None:
        rl = RateLimiter(max_attempts=3, window_seconds=60.0)
        rl.record("1.2.3.4")
        rl.record("1.2.3.4")
        rl.record("1.2.3.4")
        result = rl.check("1.2.3.4")
        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after > 0

    def test_different_keys_independent(self) -> None:
        rl = RateLimiter(max_attempts=2, window_seconds=60.0)
        rl.record("1.2.3.4")
        rl.record("1.2.3.4")
        # Different IP should still be allowed
        result = rl.check("5.6.7.8")
        assert result.allowed is True
        assert result.remaining == 2


class TestRateLimiterReset:
    """Reset clears rate limit for a key."""

    def test_reset_allows_again(self) -> None:
        rl = RateLimiter(max_attempts=2, window_seconds=60.0)
        rl.record("1.2.3.4")
        rl.record("1.2.3.4")
        assert rl.check("1.2.3.4").allowed is False

        rl.reset("1.2.3.4")
        assert rl.check("1.2.3.4").allowed is True

    def test_reset_nonexistent_key(self) -> None:
        rl = RateLimiter(max_attempts=5, window_seconds=60.0)
        rl.reset("nonexistent")  # Should not raise


class TestRateLimiterWindowExpiry:
    """Sliding window eviction."""

    def test_old_attempts_evicted(self) -> None:
        rl = RateLimiter(max_attempts=2, window_seconds=1.0)
        rl.record("1.2.3.4")
        rl.record("1.2.3.4")
        assert rl.check("1.2.3.4").allowed is False

        # Fake time advance past window
        rl._attempts["1.2.3.4"][0] = time.monotonic() - 2.0
        rl._attempts["1.2.3.4"][1] = time.monotonic() - 2.0
        assert rl.check("1.2.3.4").allowed is True

    def test_retry_after_matches_window(self) -> None:
        rl = RateLimiter(max_attempts=1, window_seconds=300.0)
        rl.record("1.2.3.4")
        result = rl.check("1.2.3.4")
        assert result.allowed is False
        assert result.retry_after > 290  # Close to 300s


class TestRateLimiterProperties:
    """Configuration properties."""

    def test_max_attempts(self) -> None:
        rl = RateLimiter(max_attempts=10, window_seconds=60.0)
        assert rl.max_attempts == 10

    def test_window_seconds(self) -> None:
        rl = RateLimiter(max_attempts=5, window_seconds=120.0)
        assert rl.window_seconds == 120.0

    def test_default_values(self) -> None:
        rl = RateLimiter()
        assert rl.max_attempts == 5
        assert rl.window_seconds == 300.0
