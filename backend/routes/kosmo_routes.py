"""
Kosmo Sync API routes — manual trigger and status.
The sync engine lives in /app/backend/kosmo_sync.py
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends

from dependencies import db, get_current_user
from kosmo_sync import run_tracking_sync

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sync", tags=["Kosmo Sync"])

_manual_sync_task: Optional[asyncio.Task] = None


@router.post("/tracking")
async def sync_tracking(user: dict = Depends(get_current_user)):
    """Manually trigger Kosmo tracking sync as a background task."""
    global _manual_sync_task

    # Check if a sync is already running
    if _manual_sync_task and not _manual_sync_task.done():
        return {"status": "in_progress", "message": "Sincronizacion ya en curso"}

    async def _run_sync():
        try:
            result = await run_tracking_sync(db)
            logger.info(
                f"Manual Kosmo sync: {result['total_checked']} checked, "
                f"{result['updated']} updated, {result['errors']} errors"
            )
        except Exception as e:
            logger.error(f"Manual Kosmo sync error: {e}")

    _manual_sync_task = asyncio.create_task(_run_sync())
    return {"status": "started", "message": "Sincronizacion iniciada en segundo plano"}


@router.get("/status")
async def get_sync_status(user: dict = Depends(get_current_user)):
    """Get the last sync timestamp and stats."""
    doc = await db.system_config.find_one(
        {"key": "kosmo_last_sync"}, {"_id": 0}
    )
    if not doc:
        return {"last_sync": None, "total_checked": 0, "updated": 0, "errors": 0}
    return {
        "last_sync": doc.get("value"),
        "total_checked": doc.get("total_checked", 0),
        "updated": doc.get("updated", 0),
        "errors": doc.get("errors", 0),
        "rate_limited": doc.get("rate_limited", False),
    }
