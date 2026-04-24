"""
MongoDB-based leader election for background tasks.

Purpose: when the app runs with multiple Uvicorn workers (prod), only ONE process
should execute:
  - ai_eval_worker (LLM-heavy jobs)
  - kosmo_sync (polling external API)
  - architecture cron

Otherwise every worker spawns its own background tasks → duplicate work, wasted
tokens, race conditions on job pickup.

Usage:
    from leader_election import acquire_leader, is_leader

    async def lifespan():
        is_leader_process = await acquire_leader(db, role="bg_tasks")
        if is_leader_process:
            asyncio.create_task(start_ai_eval_worker(db))
            asyncio.create_task(start_kosmo_sync(db))

Mechanism:
  - Each worker tries to insert a doc {role, worker_id, expires_at} in `leader_election`
  - First to succeed becomes leader; others lose
  - Leader refreshes its TTL every HEARTBEAT_SECONDS in a background coroutine
  - If leader dies, its doc expires via TTL → next worker at next boot wins
  - Simpler than Raft/etcd; sufficient for 2-5 workers

Limitations:
  - On crash, there's a grace window (≤ LEASE_SECONDS) before a new leader wins
  - Not suitable for workloads requiring zero-downtime leader transitions
"""
import os
import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

LEASE_SECONDS = int(os.environ.get("LEADER_LEASE_SECONDS", "30"))
HEARTBEAT_SECONDS = max(5, LEASE_SECONDS // 3)

_this_worker_id = f"{os.getpid()}-{uuid.uuid4().hex[:6]}"
_leader_roles: set[str] = set()
_heartbeat_tasks: dict[str, asyncio.Task] = {}


async def _ensure_index(db) -> None:
    """Create TTL index on leader_election.expires_at (idempotent)."""
    try:
        await db.leader_election.create_index("expires_at", expireAfterSeconds=0)
    except Exception:
        pass  # index already exists or insufficient perms; not fatal


async def acquire_leader(db, role: str = "bg_tasks") -> bool:
    """Try to become the leader for `role`. Returns True if this worker wins."""
    await _ensure_index(db)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=LEASE_SECONDS)

    try:
        await db.leader_election.update_one(
            {
                "role": role,
                "$or": [
                    {"worker_id": _this_worker_id},  # refresh my own lock
                    {"expires_at": {"$lt": now}},    # take over expired lock
                ],
            },
            {"$set": {
                "role": role,
                "worker_id": _this_worker_id,
                "acquired_at": now,
                "expires_at": expires,
            }},
            upsert=True,
        )
    except Exception as e:
        # Most likely: duplicate key (another worker already owns) — not leader
        logger.info(f"[leader] could not acquire {role}: {e}")
        return False

    # Verify we actually own it
    doc = await db.leader_election.find_one({"role": role}, {"_id": 0, "worker_id": 1})
    if doc and doc.get("worker_id") == _this_worker_id:
        _leader_roles.add(role)
        _heartbeat_tasks[role] = asyncio.create_task(_heartbeat_loop(db, role))
        logger.info(f"[leader] acquired '{role}' (worker={_this_worker_id})")
        return True

    logger.info(f"[leader] another worker owns '{role}' (we are {_this_worker_id})")
    return False


async def _heartbeat_loop(db, role: str):
    """Refresh the lease every HEARTBEAT_SECONDS while we remain the leader."""
    try:
        while role in _leader_roles:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            now = datetime.now(timezone.utc)
            expires = now + timedelta(seconds=LEASE_SECONDS)
            result = await db.leader_election.update_one(
                {"role": role, "worker_id": _this_worker_id},
                {"$set": {"expires_at": expires, "heartbeat_at": now}},
            )
            if result.matched_count == 0:
                logger.warning(f"[leader] lost lease for '{role}' — another worker took over")
                _leader_roles.discard(role)
                return
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"[leader] heartbeat error for '{role}': {e}")


async def release_leader(db, role: str = "bg_tasks") -> None:
    """Release leadership gracefully on shutdown."""
    _leader_roles.discard(role)
    task = _heartbeat_tasks.pop(role, None)
    if task:
        task.cancel()
    try:
        await db.leader_election.delete_one({"role": role, "worker_id": _this_worker_id})
        logger.info(f"[leader] released '{role}'")
    except Exception as e:
        logger.debug(f"[leader] release error: {e}")


def is_leader(role: str = "bg_tasks") -> bool:
    return role in _leader_roles


def worker_id() -> str:
    return _this_worker_id
