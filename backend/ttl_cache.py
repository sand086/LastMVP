"""
Tiny in-memory TTL cache decorator for read-heavy FastAPI endpoints.

Scope: per-process (no Redis, works across the single backend worker).
Key: includes user role/email when relevant so tenant-aware data doesn't leak.
Thread-safety: single-worker asyncio, no lock needed.
"""
import time
import asyncio
import hashlib
import json
from functools import wraps
from typing import Any, Callable, Optional

# Global cache store: key → (expires_at, value)
_cache: dict[str, tuple[float, Any]] = {}
_MAX_ENTRIES = 500


def _make_key(prefix: str, args: tuple, kwargs: dict, user_key: Optional[str]) -> str:
    """Build a deterministic cache key from function args."""
    blob = {
        "a": [repr(a)[:120] for a in args],
        "k": {k: repr(v)[:120] for k, v in sorted(kwargs.items()) if k != "user"},
        "u": user_key or "",
    }
    digest = hashlib.md5(json.dumps(blob, sort_keys=True).encode()).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _cleanup_if_needed():
    """Evict half the cache when it grows too large."""
    if len(_cache) <= _MAX_ENTRIES:
        return
    now = time.time()
    # Remove expired first
    for k in [k for k, (exp, _) in _cache.items() if exp < now]:
        _cache.pop(k, None)
    # If still too big, drop oldest by sorting
    if len(_cache) > _MAX_ENTRIES:
        items = sorted(_cache.items(), key=lambda kv: kv[1][0])
        for k, _ in items[: len(_cache) // 2]:
            _cache.pop(k, None)


def ttl_cache(ttl_seconds: int = 30, prefix: Optional[str] = None,
              user_scope: str = "none"):
    """Decorator to cache async endpoint responses in memory.

    Args:
        ttl_seconds: how long the entry stays fresh.
        prefix: cache bucket; defaults to function name.
        user_scope: 'none' | 'role' | 'email' — include in key to isolate tenants.
    """
    def deco(fn: Callable):
        bucket = prefix or fn.__name__

        @wraps(fn)
        async def wrapper(*args, **kwargs):
            user = kwargs.get("user") or {}
            user_key = None
            if user_scope == "role":
                user_key = user.get("role", "")
            elif user_scope == "email":
                user_key = user.get("email", "")

            key = _make_key(bucket, args, kwargs, user_key)
            now = time.time()
            hit = _cache.get(key)
            if hit and hit[0] > now:
                return hit[1]

            result = await fn(*args, **kwargs) if asyncio.iscoroutinefunction(fn) else fn(*args, **kwargs)
            _cache[key] = (now + ttl_seconds, result)
            _cleanup_if_needed()
            return result

        return wrapper
    return deco


def invalidate_prefix(prefix: str) -> int:
    """Drop all entries for a given prefix. Returns count evicted."""
    victims = [k for k in _cache if k.startswith(f"{prefix}:")]
    for k in victims:
        _cache.pop(k, None)
    return len(victims)


def cache_stats() -> dict:
    """Return size + oldest/newest for observability."""
    now = time.time()
    alive = [(k, exp) for k, (exp, _) in _cache.items() if exp > now]
    return {
        "entries": len(_cache),
        "alive": len(alive),
        "expired": len(_cache) - len(alive),
        "max": _MAX_ENTRIES,
    }
