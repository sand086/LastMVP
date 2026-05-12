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
                healed = summary.get("recovered_by_fallback", 0)
                nomatch = summary.get("no_routal_match", 0)
                if d > 0 or f > 0 or rf > 0 or healed > 0:
                    logger.info(
                        f"[routal-sync] journey={journey['id']} delivered+={d} failed+={f} "
                        f"recipient_filled+={rf} healed_service_id+={healed} "
                        f"pending={summary.get('still_pending', 0)} no_match={nomatch}"
                    )
                elif nomatch > 0:
                    # Caso ruidoso pero útil: sync corrió OK pero N packages NO
                    # matchean ningún stop ni por id ni por tracking_number.
                    # Probable causa: stops eliminados/reasignados en Routal.
                    logger.warning(
                        f"[routal-sync] journey={journey['id']} no_match={nomatch} "
                        f"packages sin stop correspondiente en Routal (stops_in_routal="
                        f"{summary.get('stops_in_routal',0)}, pkgs={summary.get('packages_in_journey',0)})"
                    )
            else:
                # Bug fix 2026-05-06: surface ok=false errors. Previously they were
                # silently swallowed and the journey kept being a candidate forever
                # without any visibility — making the user see "no updates" until
                # they manually clicked sync.
                logger.warning(
                    f"[routal-sync] journey={journey['id']} sync NOT ok: "
                    f"{summary.get('error', 'unknown')[:200]}"
                )
                # Stamp routal_synced_at anyway so we don't re-pick this journey
                # immediately next tick (creates a 5-min cooldown). When the
                # underlying issue (e.g. plan deleted on Routal side) clears,
                # the cooldown lets us retry without busy-looping.
                try:
                    from datetime import datetime, timezone
                    await db.journeys.update_one(
                        {"id": journey["id"]},
                        {"$set": {
                            "routal_synced_at": datetime.now(timezone.utc).isoformat(),
                            "routal_last_sync_error": (summary.get("error") or "")[:200],
                        }},
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"[routal-sync] error syncing journey={journey.get('id')}: {e}")


async def _tick(db):
    """Single sync tick: find candidate journeys and sync them in parallel.

    Skips journeys synced in the last MIN_RESYNC_INTERVAL_MIN minutes (default 5)
    AND already 100% delivered/failed (no pending packages) — these are stable
    and don't need re-checking until something changes.
    """
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=JOURNEY_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    min_resync_minutes = int(os.environ.get("ROUTAL_SYNC_MIN_RESYNC_MIN", "5"))
    skip_synced_after = (datetime.now(timezone.utc) - timedelta(minutes=min_resync_minutes)).isoformat()

    cursor = db.journeys.find(
        {
            "source": "routal",
            # Bug fix 2026-05-06: include "in_progress" — after iter84/iter85 the
            # status normalization landed and journeys move planificada → in_progress
            # → closed. Worker was only catching "planificada" + obsolete "en_ruta".
            "status": {"$in": ["planificada", "en_ruta", "in_progress", "scheduled"]},
            "date": {"$gte": cutoff_date},
            "routal_plan_id": {"$exists": True, "$ne": None},
            # Defensive: $not $gte covers ALL three cases:
            #   (a) field missing
            #   (b) field present but null
            #   (c) field with old timestamp (< cutoff)
            # The previous $or used $exists:False which silently skipped journeys
            # where the field was created with explicit null value at journey insert
            # — which appears to be the case for some PROD docs (e.g. f4ce8961 was
            # never synced despite being a valid candidate).
            "routal_synced_at": {"$not": {"$gte": skip_synced_after}},
        },
        {"_id": 0, "id": 1, "client_id": 1, "routal_plan_id": 1, "date": 1, "driver_name": 1,
         "packages_total": 1, "packages_delivered": 1, "packages_failed": 1},
    ).sort("date", -1).limit(200)
    journeys = [j async for j in cursor]
    # Skip already-stable journeys (all packages resolved)
    candidates = []
    for j in journeys:
        total = j.get("packages_total") or 0
        resolved = (j.get("packages_delivered") or 0) + (j.get("packages_failed") or 0)
        if total > 0 and resolved >= total:
            # already fully resolved; don't re-fetch (would still cost a Routal API call)
            continue
        candidates.append(j)
    if not candidates:
        return 0

    api_base = os.environ.get("REACT_APP_BACKEND_URL", "")
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    await asyncio.gather(*[_sync_one(db, j, api_base, sem) for j in candidates], return_exceptions=True)
    return len(candidates)


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
                # Bug fix 2026-05-06: was DEBUG, hidden in PROD. Now INFO so we
                # can verify the worker is alive and how many journeys it's processing.
                logger.info(f"[routal-sync] tick processed {count} journeys in {elapsed:.1f}s")
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
