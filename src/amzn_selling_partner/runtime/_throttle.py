"""Per-operation token buckets.

``RateLimit`` is the annotation a plugin attaches to an operation (requests per
second + burst). ``Throttler`` / ``AsyncThrottler`` keep one bucket per
operation key, seeded lazily from that annotation, and apply a server-imposed
penalty after a 429 (``x-amzn-RateLimit-Limit`` / ``Retry-After``).
"""

from __future__ import annotations

import asyncio
import random
import threading
import time
from dataclasses import dataclass


@dataclass(slots=True, frozen=True, kw_only=True)
class RateLimit:
    rate: float  # requests per second (token refill rate)
    burst: int  # bucket capacity

    def __post_init__(self) -> None:
        if self.rate <= 0 or self.burst <= 0:
            raise ValueError("rate and burst must be positive")


class TokenBucket:
    """Blocking token bucket. ``acquire`` sleeps until a token is available."""

    __slots__ = ("_burst", "_lock", "_penalty_until", "_rate", "_tokens", "_updated")

    def __init__(self, limit: RateLimit) -> None:
        self._rate = limit.rate
        self._burst = float(limit.burst)
        self._tokens = float(limit.burst)
        self._updated = time.monotonic()
        self._penalty_until = 0.0
        self._lock = threading.Lock()

    @property
    def rate(self) -> float:
        return self._rate

    def _reserve(self) -> float:
        """Take one token (possibly going negative) and return the wait time."""
        with self._lock:
            now = time.monotonic()
            self._tokens = min(self._burst, self._tokens + (now - self._updated) * self._rate)
            self._updated = now
            wait = 0.0
            if now < self._penalty_until:
                wait = self._penalty_until - now
            self._tokens -= 1.0
            if self._tokens < 0.0:
                wait = max(wait, -self._tokens / self._rate)
            return wait

    def acquire(self) -> float:
        wait = self._reserve()
        if wait > 0.0:
            time.sleep(wait)
        return wait

    def penalize(self, seconds: float, *, jitter: float = 0.25) -> None:
        """Pause the bucket after a 429 for ``seconds`` (+ up to ``jitter`` × seconds)."""
        with self._lock:
            until = time.monotonic() + seconds * (1.0 + random.random() * jitter)  # noqa: S311
            self._penalty_until = max(self._penalty_until, until)

    def update_rate(self, rate: float) -> None:
        with self._lock:
            if rate > 0:
                self._rate = rate


class AsyncTokenBucket(TokenBucket):
    """Same bucket, awaiting instead of sleeping. Safe for one event loop."""

    __slots__ = ()

    async def acquire(self) -> float:  # type: ignore[override]
        wait = self._reserve()
        if wait > 0.0:
            await asyncio.sleep(wait)
        return wait


class Throttler:
    """Registry of buckets keyed by operation key (e.g. ``"orders.v0.getOrders"``)."""

    __slots__ = ("_buckets", "_default", "_factory", "_lock")

    def __init__(self, *, default: RateLimit | None = None) -> None:
        self._buckets: dict[str, TokenBucket] = {}
        self._default = default
        self._lock = threading.Lock()
        self._factory = TokenBucket

    def bucket(self, key: str, limit: RateLimit | None) -> TokenBucket | None:
        b = self._buckets.get(key)
        if b is not None:
            return b
        limit = limit or self._default
        if limit is None:
            return None
        with self._lock:
            b = self._buckets.get(key)
            if b is None:
                b = self._factory(limit)
                self._buckets[key] = b
        return b


class AsyncThrottler(Throttler):
    __slots__ = ()

    def __init__(self, *, default: RateLimit | None = None) -> None:
        super().__init__(default=default)
        self._factory = AsyncTokenBucket


__all__ = ["AsyncThrottler", "AsyncTokenBucket", "RateLimit", "Throttler", "TokenBucket"]
