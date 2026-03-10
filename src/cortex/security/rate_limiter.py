"""In-memory sliding window rate limiter — per-IP login throttling.

No external dependencies. Tracks attempts in a deque per key,
evicts entries older than the window.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    remaining: int
    retry_after: float  # Seconds until next attempt is allowed (0 if allowed)


class RateLimiter:
    """Sliding window rate limiter.

    Tracks attempts per key (typically IP address). After `max_attempts`
    within `window_seconds`, further attempts are rejected until the
    window slides past the oldest entry.

    Args:
        max_attempts: Maximum attempts within the window.
        window_seconds: Window size in seconds.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: float = 300.0,
    ) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    @property
    def window_seconds(self) -> float:
        return self._window_seconds

    def check(self, key: str) -> RateLimitResult:
        """Check if a request is allowed without recording it.

        Returns the current rate limit status for this key.
        """
        now = time.monotonic()
        self._evict(key, now)
        attempts = self._attempts[key]
        count = len(attempts)

        if count >= self._max_attempts:
            oldest = attempts[0]
            retry_after = self._window_seconds - (now - oldest)
            return RateLimitResult(
                allowed=False,
                remaining=0,
                retry_after=max(0.0, retry_after),
            )

        return RateLimitResult(
            allowed=True,
            remaining=self._max_attempts - count,
            retry_after=0.0,
        )

    def record(self, key: str) -> RateLimitResult:
        """Record an attempt and return the updated rate limit status.

        Call this after a failed login attempt. On success, call `reset()`.
        """
        now = time.monotonic()
        self._evict(key, now)
        self._attempts[key].append(now)
        return self.check(key)

    def reset(self, key: str) -> None:
        """Reset the rate limit for a key (e.g., after successful login)."""
        self._attempts.pop(key, None)

    def _evict(self, key: str, now: float) -> None:
        """Remove attempts older than the window."""
        attempts = self._attempts[key]
        cutoff = now - self._window_seconds
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        # Clean up empty entries
        if not attempts and key in self._attempts:
            del self._attempts[key]
