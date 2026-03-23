"""
Kosmo Tracking Scraper & Sync Module
Scrapes public Kosmo tracking pages (Next.js SSR) to auto-update package statuses.
No API key required. No authentication needed against Kosmo.
"""

import asyncio
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
}

MAX_PACKAGES_PER_SYNC = 250


async def scrape_kosmo_page(tracking_url: str) -> dict:
    """
    Extracts order data from the public Kosmo tracking page.
    The page is Next.js SSR — all data lives in <script id="__NEXT_DATA__">.
    No authentication or API key required.
    """
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(tracking_url, headers=HEADERS)
            if resp.status_code != 200:
                return {"error": f"HTTP {resp.status_code}", "order_status": None}

        html = resp.text

        # Extract JSON from the standard Next.js __NEXT_DATA__ tag
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
        }

    except Exception as e:
        logger.warning(f"Error scraping {tracking_url}: {e}")
        return {"error": str(e), "order_status": None}


# ── Core sync logic ─────────────────────────────────────────────
async def run_tracking_sync(db: AsyncIOMotorDatabase) -> dict:
    """
    1. Find candidate packages (tracking_url set, not closed, not recently scraped).
    2. Scrape each (max 50, concurrency 5).
    3. Map Kosmo status → LastMile status and update MongoDB.
    4. Recalculate journey counts for affected routes.
    """
    now = datetime.now(timezone.utc)
    thirty_min_ago = now - timedelta(minutes=30)

    query = {
        "tracking_url": {"$nin": [None, ""]},
        "status": {"$nin": ["delivered", "failed"]},
        "$or": [
            {"kosmo_scraped_at": None},
            {"kosmo_scraped_at": {"$exists": False}},
            {"kosmo_scraped_at": {"$lt": thirty_min_ago.isoformat()}},
        ],
    }

    packages = await db.packages.find(
        query, {"_id": 0, "id": 1, "tracking_url": 1, "status": 1, "journey_id": 1}
    ).to_list(MAX_PACKAGES_PER_SYNC)

    if not packages:
        await db.system_config.update_one(
            {"key": "kosmo_last_sync"},
            {"$set": {
                "value": now.isoformat(),
                "total_checked": 0,
                "updated": 0,
                "errors": 0,
            }},
            upsert=True,
        )
        return {"total_checked": 0, "updated": 0, "no_change": 0, "errors": 0, "details": []}

    semaphore = asyncio.Semaphore(5)
    details = []
    updated_count = 0
    no_change_count = 0
    error_count = 0
    journey_ids_to_recount = set()

    async def process_package(pkg: dict):
        nonlocal updated_count, error_count, no_change_count
        async with semaphore:
            result = await scrape_kosmo_page(pkg["tracking_url"])

            detail = {
                "tracking_url": pkg["tracking_url"],
                "package_id": pkg["id"],
                "old_status": pkg["status"],
                "new_status": pkg["status"],
                "changed": False,
                "driver_note": None,
                "proof_count": 0,
                "error": None,
            }

            if result.get("error"):
                detail["error"] = result["error"]
                error_count += 1
                details.append(detail)
                return

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

            detail["driver_note"] = result.get("driver_note")
            detail["proof_count"] = result.get("proof_count", 0)

            if mapped_status and mapped_status != pkg["status"]:
                update_fields["status"] = mapped_status
                detail["new_status"] = mapped_status
                detail["changed"] = True
                updated_count += 1
                journey_ids_to_recount.add(pkg.get("journey_id"))
            else:
                no_change_count += 1

            await db.packages.update_one(
                {"id": pkg["id"]}, {"$set": update_fields}
            )
            details.append(detail)

    tasks = [process_package(pkg) for pkg in packages]
    await asyncio.gather(*tasks, return_exceptions=True)

    # Recalculate journey counts for affected journeys
    for j_id in journey_ids_to_recount:
        if not j_id:
            continue
        delivered = await db.packages.count_documents({"journey_id": j_id, "status": "delivered"})
        failed = await db.packages.count_documents({"journey_id": j_id, "status": "failed"})
        await db.journeys.update_one(
            {"id": j_id},
            {"$set": {"packages_delivered": delivered, "packages_failed": failed}},
        )

    # Save sync metadata
    await db.system_config.update_one(
        {"key": "kosmo_last_sync"},
        {"$set": {
            "value": now.isoformat(),
            "total_checked": len(packages),
            "updated": updated_count,
            "errors": error_count,
        }},
        upsert=True,
    )

    # Evaluate evidence scores for packages whose status changed
    changed_ids = [d["package_id"] for d in details if d.get("changed")]
    if changed_ids:
        await evaluate_packages_by_ids(db, changed_ids, journey_ids_to_recount)

    return {
        "total_checked": len(packages),
        "updated": updated_count,
        "no_change": no_change_count,
        "errors": error_count,
        "details": details,
    }


# ── Background scheduler ────────────────────────────────────────
_sync_task: Optional[asyncio.Task] = None


async def _periodic_sync(db: AsyncIOMotorDatabase):
    """Run sync every 10 minutes in the background."""
    while True:
        try:
            await asyncio.sleep(10 * 60)
            logger.info("Running scheduled Kosmo tracking sync...")
            result = await run_tracking_sync(db)
            logger.info(
                f"Kosmo sync: {result['total_checked']} checked, "
                f"{result['updated']} updated, {result['errors']} errors"
            )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Kosmo periodic sync error: {e}")


def start_periodic_sync(db: AsyncIOMotorDatabase):
    global _sync_task
    _sync_task = asyncio.create_task(_periodic_sync(db))
    logger.info("Kosmo periodic sync scheduled (every 10 min)")


def stop_periodic_sync():
    global _sync_task
    if _sync_task:
        _sync_task.cancel()
        _sync_task = None


# ── Router factory ───────────────────────────────────────────────
def create_kosmo_router(db: AsyncIOMotorDatabase, get_current_user_dep):
    router = APIRouter(prefix="/sync", tags=["Kosmo Sync"])

    @router.post("/tracking")
    async def sync_tracking(user: dict = Depends(get_current_user_dep)):
        """Manually trigger Kosmo tracking sync."""
        result = await run_tracking_sync(db)
        return result

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
        }

    return router
