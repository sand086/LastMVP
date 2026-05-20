"""Mongo connection + collection accessors.

InnoDB equivalent: Motor async driver. Index management lives in
``seeds/initial_schema.py``.

Connection options:
- retryWrites=True — Motor default, retries idempotent writes once.
- retryReads=True — explicit, retries reads on transient errors.
- serverSelectionTimeoutMS=5000 — fail fast (instead of 30s default) if Mongo
  is unreachable. Useful for tests and pytest fixtures.
- maxPoolSize=20 — small enough to avoid pool exhaustion when many test
  files create+tear-down clients in rapid sequence.
"""
from __future__ import annotations
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from .config import MONGO_URL, DB_NAME

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(
            MONGO_URL,
            retryWrites=True,
            retryReads=True,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10_000,
            socketTimeoutMS=20_000,
            maxPoolSize=100,
            minPoolSize=0,
            # directConnection skips SDAM heartbeat monitor — safe for our
            # standalone Mongo deployment and removes a class of background
            # tasks that don't survive event-loop churn between pytest tests.
            directConnection=True,
            # Force a short heartbeat so server-side connection reaping is
            # detected fast (helps when tests churn clients between tests).
            heartbeatFrequencyMS=10_000,
        )
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[DB_NAME]


async def ping() -> bool:
    try:
        await get_client().admin.command("ping")
        return True
    except Exception:  # noqa: BLE001
        return False
