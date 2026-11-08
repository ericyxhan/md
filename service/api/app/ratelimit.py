"""In-process token-bucket rate limiting for the public API.

The API deliberately runs as a single process with SQLite, so a small
thread-safe in-memory limiter is sufficient.  Internal worker routes and health
checks are not limited; only authenticated public requests are charged.

The limiter is keyed by owner ID.  All public callers currently share the
single configured owner, which matches the v1 static-token model.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class TokenBucketRateLimiter:
    """Allow ``capacity`` requests per minute with a full initial burst."""

    def __init__(self, requests_per_minute: int):
        self.capacity = float(max(0, requests_per_minute))
        self.refill_per_second = self.capacity / 60.0
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.capacity > 0

    def consume(self, key: str, *, now: float | None = None) -> int | None:
        """Charge one request.

        Returns ``None`` when the request is allowed, or the number of seconds
        to wait before retrying when the bucket is empty.
        """

        if not self.enabled:
            return None

        current = time.monotonic() if now is None else now
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self.capacity, updated_at=current)
                self._buckets[key] = bucket

            elapsed = max(0.0, current - bucket.updated_at)
            bucket.tokens = min(
                self.capacity,
                bucket.tokens + elapsed * self.refill_per_second,
            )
            bucket.updated_at = current

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return None

            deficit = 1.0 - bucket.tokens
            return max(1, math.ceil(deficit / self.refill_per_second))

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)
