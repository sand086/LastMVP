"""
Kosmo Tracking Scraper & Sync Module
Scrapes public Kosmo tracking pages (Next.js SSR) to auto-update package statuses.
No API key required. No authentication needed against Kosmo.

Features:
- Adaptive sync frequency based on route age
- Active window: 06:00-23:00 CDMX (UTC-6)
- Per-journey sync timestamps
- Connection pooling with shared httpx client
- Concurrent scraping with configurable parallelism
- HTTP 429 rate-limit detection with exponential backoff
- Batched journey recount via aggregation
"""

import asyncio
import os
import re
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from evidence_scoring import evaluate_packages_by_ids

logger = logging.getLogger(__name__)

# ── Status Map: Kosmo → LastMile OS ────────────────────────────
STATUS_MAP = {
    "delivered": "delivered",
    "completed": "delivered",
    "cancelled": "failed",
    "failed": "failed",
    "in_transit": "pending",
    "to_pickup": "pending",
    "picked_up": "pending",
    "assigned": "pending",
    "created": "pending",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "es-MX,es;q=0.9",
}

# ── Performance Tuning ──────────────────────────────────────────
MAX_PACKAGES_PER_SYNC = 250
SCRAPE_CONCURRENCY = 10
SCHEDULER_CHECK_SECONDS = int(os.environ.get("KOSMO_SCHEDULER_CHECK_SECONDS", "90"))
MAX_JOURNEYS_PER_CYCLE = int(os.environ.get("KOSMO_MAX_JOURNEYS_PER_CYCLE", "20"))
HTTP_TIMEOUT = 12
MAX_RETRIES_ON_429 = 2
BACKOFF_BASE_SECONDS = 3

# ── Adaptive Scheduling Config ──────────────────────────────────
CDMX_UTC_OFFSET = timedelta(hours=-6)
ACTIVE_WINDOW_START = 6   # 06:00 CDMX
ACTIVE_WINDOW_END = 23    # 23:00 CDMX

# Sync intervals by route age (days old → minutes)
SYNC_INTERVALS = [
    (0, 3),      # Same day: every 3 min
    (1, 10),     # 1 day old: every 10 min
    (2, 30),     # 2 days old: every 30 min
    (3, 60),     # 3 days old: every 60 min
    (4, 180),    # 4 days old: every 180 min
    (5, 360),    # 5+ days old: every 360 min
]


def _get_cdmx_now() -> datetime:
    """Get current time in CDMX (UTC-6)."""
    return datetime.now(timezone.utc) + CDMX_UTC_OFFSET


def _is_within_active_window() -> bool:
    """Check if current CDMX time is within the active sync window."""
    cdmx_now = _get_cdmx_now()
    return ACTIVE_WINDOW_START <= cdmx_now.hour < ACTIVE_WINDOW_END


def _get_sync_interval_minutes(route_date_str: str) -> int:
    """Calculate sync interval based on route age."""
    try:
        route_date = datetime.strptime(route_date_str[:10], "%Y-%m-%d")
        cdmx_now = _get_cdmx_now()
        age_days = (cdmx_now.replace(tzinfo=None) - route_date).days
        for max_age, interval in SYNC_INTERVALS:
            if age_days <= max_age:
                return interval
        return SYNC_INTERVALS[-1][1]
    except (ValueError, TypeError):
        return 30


# ── Shared HTTP client ──────────────────────────────────────────
_http_client: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    """Get or create a shared, connection-pooled HTTP client."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=SCRAPE_CONCURRENCY + 5,
                max_keepalive_connections=SCRAPE_CONCURRENCY,
                keepalive_expiry=30,
            ),
            headers=HEADERS,
        )
    return _http_client


async def close_http_client():
    """Gracefully close the shared HTTP client on shutdown."""
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


async def scrape_kosmo_page(tracking_url: str) -> dict:
    """
    Extracts order data from the public Kosmo tracking page.
    The page is Next.js SSR — all data lives in <script id="__NEXT_DATA__">.
    Uses shared connection-pooled client. Retries on HTTP 429.
    """
    client = _get_http_client()
    last_error = None

    for attempt in range(MAX_RETRIES_ON_429 + 1):
        try:
            resp = await client.get(tracking_url)

            if resp.status_code == 429:
                wait = BACKOFF_BASE_SECONDS * (2 ** attempt)
                logger.warning(f"HTTP 429 on {tracking_url}, backoff {wait}s (attempt {attempt + 1})")
                last_error = "HTTP 429 rate limited"
                await asyncio.sleep(wait)
                continue

            if resp.status_code != 200:
                return {"error": f"HTTP {resp.status_code}", "order_status": None}

            html = resp.text
            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                html,
                re.DOTALL,
            )
            if not match:
                return {"error": "No __NEXT_DATA__ found", "order_status": None}

            data = json.loads(match.group(1))
            order = (
                data.get("props", {})
                .get("pageProps", {})
                .get("delivery", {})
                .get("order", {})
            )
            if not order:
                return {"error": "No order object in __NEXT_DATA__", "order_status": None}

            recipient = order.get("recipient", {})
            proof_of_deliveries = recipient.get("proofOfDeliveries") or []
            proof_urls = []
            for proof in proof_of_deliveries:
                if isinstance(proof, dict):
                    url = proof.get("url") or proof.get("photoUrl") or proof.get("imageUrl")
                    if url:
                        proof_urls.append(url)
                elif isinstance(proof, str):
                    proof_urls.append(proof)

            return {
                "error": None,
                "order_status": order.get("status"),
                "order_id": order.get("orderID"),
                "updated_at_ms": order.get("updatedAt"),
                "order_ref_id": recipient.get("orderReferenceId"),
                "recipient_status": recipient.get("status"),
                "finished_at_ms": recipient.get("finishedAt"),
                "driver_note": recipient.get("noteFromDriver"),
                "proof_count": len(proof_of_deliveries),
                "proof_urls": proof_urls,
            }

        except httpx.TimeoutException:
            return {"error": "timeout", "order_status": None}
        except Exception as e:
            logger.warning(f"Error scraping {tracking_url}: {e}")
            return {"error": str(e), "order_status": None}

    return {"error": last_error or "max retries exceeded", "order_status": None}


def _build_sync_query(journey_ids_filter: list = None, freshness_minutes: int = 3) -> dict:
    """Build the MongoDB query for finding packages eligible for sync.
    
    freshness_minutes controls how recently a package must have been scraped
    to be skipped. Defaults to 3 min for same-day aggressive syncing.
    """
    now = datetime.now(timezone.utc)
    freshness_cutoff = now - timedelta(minutes=freshness_minutes)
    # Terminal packages get re-scraped every 15 min to catch late Kosmo updates
    terminal_refresh_cutoff = now - timedelta(minutes=15)

    base_or = [
        # Active packages not recently scraped
        {"status": {"$nin": ["delivered", "failed", "returned"]},
         "$or": [
             {"kosmo_scraped_at": None},
             {"kosmo_scraped_at": {"$exists": False}},
             {"kosmo_scraped_at": {"$lt": freshness_cutoff.isoformat()}},
         ]},
        # Terminal packages never scraped
        {"status": {"$in": ["delivered", "failed"]},
         "$or": [
             {"kosmo_scraped_at": None},
             {"kosmo_scraped_at": {"$exists": False}},
         ]},
        # Terminal packages missing proof — rescrape after freshness cutoff
        {"status": {"$in": ["delivered", "failed"]},
         "$or": [
             {"kosmo_proof_count": 0},
             {"kosmo_proof_count": None},
             {"kosmo_proof_count": {"$exists": False}},
         ],
         "kosmo_scraped_at": {"$lt": freshness_cutoff.isoformat()}},
        # Terminal packages WITH proof — periodic refresh to catch late Kosmo updates
        {"status": {"$in": ["delivered", "failed"]},
         "kosmo_proof_count": {"$gt": 0},
         "kosmo_scraped_at": {"$lt": terminal_refresh_cutoff.isoformat()}},
        # Unknown status packages
        {"kosmo_status_raw": {"$in": ["unknown", None]},
         "kosmo_scraped_at": {"$lt": freshness_cutoff.isoformat()}},
    ]

    query = {"tracking_url": {"$nin": [None, ""]}, "$or": base_or}
    if journey_ids_filter:
        query["journey_id"] = {"$in": journey_ids_filter}
    return query


def _map_scrape_to_update(result: dict, pkg: dict, now: datetime) -> tuple:
    """Map a scrape result to (update_fields, detail, status_changed)."""
    kosmo_raw = result.get("order_status") or "unknown"
    mapped_status = STATUS_MAP.get(kosmo_raw)

    update_fields = {
        "kosmo_scraped_at": now.isoformat(),
        "kosmo_status_raw": kosmo_raw,
        "kosmo_order_id": result.get("order_id"),
    }
    if result.get("updated_at_ms"):
        update_fields["kosmo_updated_at"] = result["updated_at_ms"]
    if result.get("finished_at_ms"):
        update_fields["kosmo_finished_at"] = result["finished_at_ms"]
    if result.get("driver_note"):
        update_fields["kosmo_driver_note"] = result["driver_note"]
    update_fields["kosmo_proof_count"] = result.get("proof_count", 0)
    if result.get("proof_urls"):
        update_fields["kosmo_proof_urls"] = result["proof_urls"]

    detail = {
        "tracking_url": pkg["tracking_url"],
        "package_id": pkg["id"],
        "old_status": pkg["status"],
        "new_status": pkg["status"],
        "changed": False,
        "driver_note": result.get("driver_note"),
        "proof_count": result.get("proof_count", 0),
        "error": None,
    }

    changed = False
    if mapped_status and mapped_status != pkg["status"]:
        update_fields["status"] = mapped_status
        detail["new_status"] = mapped_status
        detail["changed"] = True
        changed = True

    return update_fields, detail, changed


async def _recount_and_update_journeys(db, journey_ids_to_recount: set, affected_journey_ids: list, now: datetime):
    """Recalculate package counts using aggregation and update sync timestamps."""
    # Batch recount using aggregation pipeline instead of individual count queries
    if journey_ids_to_recount:
        recount_list = [j for j in journey_ids_to_recount if j]
        if recount_list:
            pipeline = [
                {"$match": {"journey_id": {"$in": recount_list}, "status": {"$in": ["delivered", "failed"]}}},
                {"$group": {
                    "_id": {"journey_id": "$journey_id", "status": "$status"},
                    "count": {"$sum": 1},
                }},
            ]
            counts = {}
            async for doc in db.packages.aggregate(pipeline):
                j_id = doc["_id"]["journey_id"]
                status = doc["_id"]["status"]
                if j_id not in counts:
                    counts[j_id] = {"delivered": 0, "failed": 0}
                counts[j_id][status] = doc["count"]

            # Batch update journeys
            update_ops = []
            for j_id in recount_list:
                c = counts.get(j_id, {"delivered": 0, "failed": 0})
                update_ops.append(
                    db.journeys.update_one(
                        {"id": j_id},
                        {"$set": {"packages_delivered": c["delivered"], "packages_failed": c["failed"]}},
                    )
                )
            if update_ops:
                await asyncio.gather(*update_ops)

    # Update sync timestamps for all affected journeys
    if affected_journey_ids:
        await db.journeys.update_many(
            {"id": {"$in": affected_journey_ids}},
            {"$set": {"last_sync_at": now.isoformat()}},
        )
        # Fetch journey dates in one query and compute next_sync_at
        journeys = await db.journeys.find(
            {"id": {"$in": affected_journey_ids}},
            {"_id": 0, "id": 1, "date": 1},
        ).to_list(len(affected_journey_ids))

        update_ops = []
        for j in journeys:
            interval = _get_sync_interval_minutes(j.get("date", ""))
            next_sync = now + timedelta(minutes=interval)
            update_ops.append(
                db.journeys.update_one(
                    {"id": j["id"]},
                    {"$set": {"next_sync_at": next_sync.isoformat()}},
                )
            )
        if update_ops:
            await asyncio.gather(*update_ops)


# ── Core sync logic ─────────────────────────────────────────────
async def run_tracking_sync(db: AsyncIOMotorDatabase, journey_ids_filter: list = None) -> dict:
    """
    1. Find candidate packages (tracking_url set, not closed, not recently scraped).
    2. Scrape each (max 250, concurrency 10) using shared HTTP client.
    3. Map Kosmo status → LastMile status and update MongoDB.
    4. Recalculate journey counts for affected routes (batched aggregation).
    5. Update journey sync timestamps.
    6. Trigger AI evaluation only for packages whose status changed.
    """
    now = datetime.now(timezone.utc)
    query = _build_sync_query(journey_ids_filter)

    packages = await db.packages.find(
        query, {"_id": 0, "id": 1, "tracking_url": 1, "status": 1, "journey_id": 1}
    ).to_list(MAX_PACKAGES_PER_SYNC)

    if not packages:
        await db.system_config.update_one(
            {"key": "kosmo_last_sync"},
            {"$set": {"value": now.isoformat(), "total_checked": 0, "updated": 0, "errors": 0}},
            upsert=True,
        )
        return {"total_checked": 0, "updated": 0, "no_change": 0, "errors": 0, "details": []}

    semaphore = asyncio.Semaphore(SCRAPE_CONCURRENCY)
    details = []
    updated_count = 0
    no_change_count = 0
    error_count = 0
    journey_ids_to_recount = set()
    changed_package_ids = []
    rate_limited = False

    async def process_package(pkg: dict):
        nonlocal updated_count, error_count, no_change_count, rate_limited
        async with semaphore:
            if rate_limited:
                # If we've been rate-limited, mark remaining as skipped
                details.append({
                    "tracking_url": pkg["tracking_url"], "package_id": pkg["id"],
                    "old_status": pkg["status"], "new_status": pkg["status"],
                    "changed": False, "driver_note": None, "proof_count": 0,
                    "error": "skipped_rate_limit",
                })
                error_count += 1
                return

            result = await scrape_kosmo_page(pkg["tracking_url"])

            if result.get("error"):
                if "429" in str(result["error"]):
                    rate_limited = True
                details.append({
                    "tracking_url": pkg["tracking_url"], "package_id": pkg["id"],
                    "old_status": pkg["status"], "new_status": pkg["status"],
                    "changed": False, "driver_note": None, "proof_count": 0,
                    "error": result["error"],
                })
                error_count += 1
                return

            update_fields, detail, changed = _map_scrape_to_update(result, pkg, now)
            if changed:
                updated_count += 1
                journey_ids_to_recount.add(pkg.get("journey_id"))
                changed_package_ids.append(pkg["id"])
            else:
                no_change_count += 1

            await db.packages.update_one({"id": pkg["id"]}, {"$set": update_fields})
            details.append(detail)

    tasks = [process_package(pkg) for pkg in packages]
    await asyncio.gather(*tasks, return_exceptions=True)

    # Recalculate journey counts and update sync timestamps
    affected_journey_ids = list({pkg.get("journey_id") for pkg in packages if pkg.get("journey_id")})
    await _recount_and_update_journeys(db, journey_ids_to_recount, affected_journey_ids, now)

    # Save sync metadata
    await db.system_config.update_one(
        {"key": "kosmo_last_sync"},
        {"$set": {
            "value": now.isoformat(),
            "total_checked": len(packages),
            "updated": updated_count,
            "errors": error_count,
            "rate_limited": rate_limited,
        }},
        upsert=True,
    )

    # Evaluate evidence scores ONLY for packages whose status changed
    if changed_package_ids:
        changed_journey_ids = set(
            pkg.get("journey_id") for pkg in packages
            if pkg.get("journey_id") and pkg["id"] in changed_package_ids
        )
        await evaluate_packages_by_ids(db, changed_package_ids, changed_journey_ids)

    return {
        "total_checked": len(packages),
        "updated": updated_count,
        "no_change": no_change_count,
        "errors": error_count,
        "rate_limited": rate_limited,
        "details": details,
    }


# ── Background scheduler (Adaptive) ─────────────────────────────
_sync_task: Optional[asyncio.Task] = None


async def _adaptive_periodic_sync(db: AsyncIOMotorDatabase):
    """
    Adaptive sync scheduler that checks every 45s which journeys are due.
    Only syncs within active window (06:00-23:00 CDMX).
    Processes up to 25 journeys per cycle for faster coverage.
    """
    while True:
        try:
            await asyncio.sleep(SCHEDULER_CHECK_SECONDS)

            if not _is_within_active_window():
                continue

            now = datetime.now(timezone.utc)
            three_days_ago = (now - timedelta(days=3)).strftime("%Y-%m-%d")

            # Find journeys that are due for sync
            # Include active routes + recently closed routes (last 3 days)
            due_journeys = await db.journeys.find(
                {"$and": [
                    {"$or": [
                        {"status": {"$in": ["scheduled", "in_progress"]}},
                        {"status": "closed", "date": {"$gte": three_days_ago}},
                    ]},
                    {"$or": [
                        {"next_sync_at": {"$exists": False}},
                        {"next_sync_at": None},
                        {"next_sync_at": {"$lte": now.isoformat()}},
                    ]},
                ]},
                {"_id": 0, "id": 1, "date": 1},
            ).sort("next_sync_at", 1).to_list(MAX_JOURNEYS_PER_CYCLE)

            if not due_journeys:
                continue

            journey_ids = [j["id"] for j in due_journeys]
            logger.info(f"Adaptive sync: {len(journey_ids)} journeys due")

            result = await run_tracking_sync(db, journey_ids_filter=journey_ids)
            logger.info(
                f"Adaptive sync: {result['total_checked']} checked, "
                f"{result['updated']} updated, {result['errors']} errors"
                f"{', RATE LIMITED' if result.get('rate_limited') else ''}"
            )

            # If rate-limited, pause extra to let Kosmo cool down
            if result.get("rate_limited"):
                logger.warning("Rate limited by Kosmo, pausing 60s before next cycle")
                await asyncio.sleep(60)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Adaptive sync error: {e}")


def start_periodic_sync(db: AsyncIOMotorDatabase):
    global _sync_task
    _sync_task = asyncio.create_task(_adaptive_periodic_sync(db))
    logger.info(f"Kosmo adaptive sync started (check every {SCHEDULER_CHECK_SECONDS}s, concurrency {SCRAPE_CONCURRENCY})")


def stop_periodic_sync():
    global _sync_task
    if _sync_task:
        _sync_task.cancel()
        _sync_task = None


# ── Router factory ───────────────────────────────────────────────
def create_kosmo_router(db: AsyncIOMotorDatabase, get_current_user_dep):
    router = APIRouter(prefix="/sync", tags=["Kosmo Sync"])

    _manual_sync_task: Optional[asyncio.Task] = None

    @router.post("/tracking")
    async def sync_tracking(user: dict = Depends(get_current_user_dep)):
        """Manually trigger Kosmo tracking sync as a background task."""
        nonlocal _manual_sync_task

        if _manual_sync_task and not _manual_sync_task.done():
            return {"status": "in_progress", "message": "Sincronización ya en curso"}

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
        return {"status": "started", "message": "Sincronización iniciada en segundo plano"}

    @router.get("/status")
    async def get_sync_status(user: dict = Depends(get_current_user_dep)):
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

    return router
