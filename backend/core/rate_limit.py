"""In-memory rate limiter — free Redis alternative for the MVP bootstrap.

Sliding window per identifier (e.g. ``ip:email`` for /login).
Process-local; replace with Redis in V1 once available.
"""
from __future__ import annotations
import time
from collections import defaultdict, deque
from threading import Lock

_buckets: dict[str, deque[float]] = defaultdict(deque)
_lockouts: dict[str, float] = {}
_lock = Lock()


def hit(identifier: str, *, max_hits: int, window_seconds: int) -> tuple[bool, int]:
    """Record a hit. Returns (allowed, retry_after_seconds)."""
    now = time.time()
    with _lock:
        # Locked out?
        until = _lockouts.get(identifier)
        if until is not None:
            if now < until:
                return False, int(until - now)
            _lockouts.pop(identifier, None)

        bucket = _buckets[identifier]
        cutoff = now - window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        bucket.append(now)
        if len(bucket) > max_hits:
            return False, window_seconds
        return True, 0


def lockout(identifier: str, seconds: int) -> None:
    with _lock:
        _lockouts[identifier] = time.time() + seconds


def reset(identifier: str) -> None:
    with _lock:
        _buckets.pop(identifier, None)
        _lockouts.pop(identifier, None)
