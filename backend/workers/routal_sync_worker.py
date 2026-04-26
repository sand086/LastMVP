"""
Routal periodic sync worker (R00C / iter65).

Polls every N minutes (env: ROUTAL_SYNC_INTERVAL_MINUTES, default 10) and runs
sync_journey_from_routal for all active Routal journeys (status in
{'planificada', 'en_ruta'}). Gated by leader_election to avoid duplicate work
across multi-worker deploys.

This worker is the safety net for missed/delayed `stop.completed` webhooks: it
ensures status + evidence on Routal-sourced journeys converge to ground truth
within ROUTAL_SYNC_INTERVAL_MINUTES regardless of webhook reliability.
"""
import os
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

INTERVAL_MIN = int(os.environ.get("ROUTAL_SYNC_INTERVAL_MINUTES", "10"))
MAX_CONCURRENT = int(os.environ.get("ROUTAL_SYNC_MAX_CONCURRENT", "3"))
JOURNEY_LOOKBACK_DAYS = int(os.environ.get("ROUTAL_SYNC_LOOKBACK_DAYS", "7"))

_task: Optional[asyncio.Task] = None


async def _sync_one(db, journey, api_base, sem):
    """Sync a single journey under semaphore. Errors logged but not re-raised."""
    from services.routal_sync import sync_journey_from_routal
    async with sem:
        try:
            summary = await sync_journey_from_routal(db, journey["id"], api_base)
            if summary.get("ok"):
                d = summary.get("delivered_synced", 0)
                f = summary.get("failed_synced", 0)
                rf = summary.get("recipient_filled", 0)
                if d > 0 or f > 0 or rf > 0:
                    logger.info(
                        f"[routal-sync] journey={journey['id']} delivered+={d} failed+={f} "
                        f"recipient_filled+={rf} pending={summary.get('still_pending', 0)}"
                    )
        except Exception as e:
            logger.error(f"[routal-sync] error syncing journey={journey.get('id')}: {e}")


async def _tick(db):
    """Single sync tick: find candidate journeys and sync them in parallel."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=JOURNEY_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    cursor = db.journeys.find(
        {
            "source": "routal",
            "status": {"$in": ["planificada", "en_ruta"]},
            "date": {"$gte": cutoff},
            "routal_plan_id": {"$exists": True, "$ne": None},
        },
        {"_id": 0, "id": 1, "client_id": 1, "routal_plan_id": 1, "date": 1, "driver_name": 1},
    ).sort("date", -1).limit(200)
    journeys = [j async for j in cursor]
    if not journeys:
        return 0

    api_base = os.environ.get("REACT_APP_BACKEND_URL", "")
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    await asyncio.gather(*[_sync_one(db, j, api_base, sem) for j in journeys], return_exceptions=True)
    return len(journeys)


async def _loop(db):
    """Main loop: sleep INTERVAL_MIN minutes between ticks. Cancellable."""
    logger.info(f"[routal-sync] worker started · interval={INTERVAL_MIN}min · concurrent={MAX_CONCURRENT}")
    # Initial small delay so app finishes booting
    await asyncio.sleep(30)
    try:
        while True:
            try:
                t0 = datetime.now(timezone.utc)
                count = await _tick(db)
                elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
                logger.debug(f"[routal-sync] tick processed {count} journeys in {elapsed:.1f}s")
            except Exception as e:
                logger.error(f"[routal-sync] tick error: {e}")
            await asyncio.sleep(INTERVAL_MIN * 60)
    except asyncio.CancelledError:
        logger.info("[routal-sync] worker cancelled")
        raise


def start_routal_sync_worker(db):
    global _task
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop(db))


def stop_routal_sync_worker():
    global _task
    if _task and not _task.done():
        _task.cancel()
