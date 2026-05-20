"""System routes — /api/system/health (P0.11), /api/system/version."""
from __future__ import annotations
from fastapi import APIRouter

from core.config import APP_VERSION
from core.db import ping
from core.response import ok

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health")
async def health():
    db_ok = await ping()
    return ok({
        "db": "ok" if db_ok else "down",
        "redis": "n/a",  # in-memory rate limiter — Redis is not used in MVP bootstrap
        "version": APP_VERSION,
    })


@router.get("/version")
async def version():
    return ok({"version": APP_VERSION})
