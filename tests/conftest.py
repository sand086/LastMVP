"""Pytest fixtures — async Mongo + 2 fake tenants for isolation tests.

Strategy:
- Motor binds to the loop where it was first awaited. pytest-asyncio creates
  a fresh loop per test (mode=auto + default function scope), so each test
  needs its OWN Motor client instance.
- We reset ``core.db._client = None`` between tests (sync autouse) so the
  next ``get_client()`` call creates a fresh instance bound to the new loop.
- We do NOT explicitly call ``client.close()`` because doing so during
  teardown can cause "Cannot use MongoClient after close" errors when the
  app under test has captured Database/Collection references that we can't
  invalidate. Letting GC reap the previous client works fine in practice.
- The ``db`` fixture wraps ``drop_database`` in retry-on-AutoReconnect — the
  only place AutoReconnect surfaces is right at the start of a test when the
  pool is being warmed up against MongoDB and the previous test's pool is
  still being torn down by the OS.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

# Ensure backend is importable BEFORE any project import
BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env")

# Force tests to use an isolated database
os.environ["DB_NAME"] = (os.environ.get("DB_NAME", "test_database") + "_pytest")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

import core.db as core_db  # noqa: E402
from core.uuid import new_id  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _reset_motor_client():
    """Force a fresh Motor client + warm the connection pool BEFORE each test.

    Strategy explained:
    - We MUST reset the client between tests because Motor binds to the
      first event loop it sees, and pytest-asyncio creates a fresh loop per
      test.
    - We MUST force GC of the previous client BEFORE creating the new one
      so its sockets are reaped by the OS before pymongo tries to reuse
      ports/FDs.
    - We MUST warm the new pool with a ping before yielding. The ping loop
      retries on AutoReconnect (the typical cold-start race after the
      previous test's pool teardown).
    - We additionally wrap each Motor collection method on the freshly
      created client so that ANY operation issued during a test fixture's
      setup retries automatically on AutoReconnect — this catches the case
      where ``db.tenants.insert_many(...)`` in a test-specific setup hits
      a stale socket that the warm-up ping happened to skip.
    - Iter33 — limpiamos `_buckets` y `_lockouts` del rate_limit global
      para evitar contaminación cross-test cuando tests hacen >240 requests
      en suite completa (ThrottleMiddleware: 240 req/min/IP).
    """
    import asyncio
    import gc
    from pymongo.errors import AutoReconnect

    # Reset rate limit state global (ThrottleMiddleware + per-endpoint limits).
    try:
        from core import rate_limit as _rl
        _rl._buckets.clear()
        _rl._lockouts.clear()
    except Exception:  # noqa: BLE001
        pass
    # Reset rate limit local del CP lookup (iter32).
    try:
        from routes import util_cp as _cp
        _cp._rate_limit.clear()
    except Exception:  # noqa: BLE001
        pass

    core_db._client = None
    gc.collect()

    # Warm the pool with retries so the very first op of the next test sees
    # a healthy socket.
    for attempt in range(5):
        try:
            await core_db.get_client().admin.command("ping")
            break
        except AutoReconnect:
            core_db._client = None
            gc.collect()
            await asyncio.sleep(0.05 * (attempt + 1))

    # Patch the freshly created client so transient AutoReconnect during the
    # FIRST operation of any test fixture is retried instead of bubbled up.
    _wrap_for_retries(core_db.get_client())

    yield
    core_db._client = None
    gc.collect()


def _wrap_for_retries(client):
    """Wrap selected pymongo collection-level coroutines with retry-on-AutoReconnect.

    Motor exposes its collection methods at runtime via ``__getattr__`` on
    ``AsyncIOMotorCollection`` — we monkey-patch the methods whose first call
    of the test most often hits the stale-socket race (insert/find/update).
    """
    import functools
    from pymongo.errors import AutoReconnect
    from motor.motor_asyncio import AsyncIOMotorCollection

    if getattr(AsyncIOMotorCollection, "_mye_retry_patched", False):
        return

    methods = [
        "insert_one", "insert_many", "find_one", "update_one", "update_many",
        "delete_one", "delete_many", "count_documents", "replace_one",
        "find_one_and_update", "find_one_and_replace", "find_one_and_delete",
        "drop", "create_index", "create_indexes", "index_information",
        "aggregate_to_list",
    ]
    for name in methods:
        original = getattr(AsyncIOMotorCollection, name, None)
        if original is None or not callable(original):
            continue

        @functools.wraps(original)
        async def _retrying(self, *args, _orig=original, _name=name, **kwargs):
            import asyncio as _aio
            last = None
            for i in range(3):
                try:
                    return await _orig(self, *args, **kwargs)
                except AutoReconnect as e:
                    last = e
                    # Pymongo's pool will rebuild on its own; we just back
                    # off briefly and let the next attempt re-checkout.
                    await _aio.sleep(0.05 * (i + 1))
            raise last

        setattr(AsyncIOMotorCollection, name, _retrying)
    AsyncIOMotorCollection._mye_retry_patched = True


async def _safe_op(coro_factory, max_retries: int = 3):
    """Run an async DB operation with retry-on-AutoReconnect.

    AutoReconnect is raised by pymongo when a socket has been closed by the
    server (or OS) between checkout and use. Retrying on a fresh client
    side-steps the stale-pool race that surfaces between rapid pytest tests.
    """
    from pymongo.errors import AutoReconnect

    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            return await coro_factory()
        except AutoReconnect as e:
            last_err = e
            # Stale pool — drop the cached client so the next call rebuilds it.
            core_db._client = None
    if last_err is not None:
        raise last_err


@pytest_asyncio.fixture(scope="function")
async def db():
    name = os.environ["DB_NAME"]
    await _safe_op(lambda: core_db.get_client().drop_database(name))
    database = core_db.get_client()[name]
    yield database
    await _safe_op(lambda: core_db.get_client().drop_database(name))


@pytest_asyncio.fixture(scope="function")
async def two_tenants(db):
    a_id, b_id = new_id(), new_id()
    await db.tenants.insert_many([
        {"id": a_id, "slug": "tenant-a", "name": "Tenant A", "status": "active"},
        {"id": b_id, "slug": "tenant-b", "name": "Tenant B", "status": "active"},
    ])
    return {"a": a_id, "b": b_id, "db": db}
