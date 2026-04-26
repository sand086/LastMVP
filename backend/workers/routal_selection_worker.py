"""
Routal selection worker (R00B / PROMPT-SEL01).

Daily 2-phase audit selection algorithm. Idempotent. Multi-tenant.

Algorithm:
  Phase 1 (priority): drivers NOT audited yesterday.
  Phase 2 (rotation): drivers audited yesterday, ordered by 30d audit count (asc).
  Tie-break: deterministic shuffle seeded by target_date (YYYYMMDD).

Persistence:
  - routal_daily_plans: staging buffer (filled by _handle_plan_created when
    selection_enabled=True).
  - driver_audit_log: source of truth for "selected" / "unselected" decisions.
  - journeys: created ONLY for selected drivers (via _handle_plan_created_direct).
"""
import asyncio
import logging
import random
from datetime import datetime, date, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CDMX_TZ = ZoneInfo("America/Mexico_City")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_cdmx() -> date:
    return datetime.now(CDMX_TZ).date()


def _date_to_dt(d: date) -> datetime:
    """Convert date → datetime at 00:00 UTC (used as Mongo storage key)."""
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _seed_for_date(d: date) -> int:
    return int(d.strftime("%Y%m%d"))


# ─────────────── ALGORITHM ───────────────

def _select_drivers(
    drivers_today: list,
    audited_yesterday: set,
    audit_counts: dict,
    max_daily: int,
    target_date: date,
) -> tuple[list, dict]:
    """Pure function. Returns (selected_drivers, phase_map).

    phase_map: {driver_id: 'phase_1' | 'phase_2'}
    """
    rng = random.Random(_seed_for_date(target_date))

    not_yesterday = [d for d in drivers_today if d not in audited_yesterday]
    from_yesterday = [d for d in drivers_today if d in audited_yesterday]

    if len(drivers_today) <= max_daily:
        # Fits entirely; mark phase per origin
        phase_map = {d: ("phase_1" if d in not_yesterday else "phase_2") for d in drivers_today}
        return list(drivers_today), phase_map

    if len(not_yesterday) >= max_daily:
        # PHASE 1 PURE: random sample from not_yesterday
        shuffled = list(not_yesterday)
        rng.shuffle(shuffled)
        selected = shuffled[:max_daily]
        return selected, {d: "phase_1" for d in selected}

    if not_yesterday:
        # PHASE 1 PARTIAL + PHASE 2: take all not_yesterday, fill with lowest audit_count
        selected = list(not_yesterday)
        remaining = max_daily - len(selected)
        # Stable shuffle then stable sort by count → deterministic tie-break
        candidates = list(from_yesterday)
        rng.shuffle(candidates)
        candidates.sort(key=lambda d: audit_counts.get(d, 0))
        phase_2_picks = candidates[:remaining]
        selected.extend(phase_2_picks)
        phase_map = {d: "phase_1" for d in not_yesterday}
        for d in phase_2_picks:
            phase_map[d] = "phase_2"
        return selected, phase_map

    # PHASE 2 PURE: every driver was audited yesterday → fall back to count-based rotation
    candidates = list(drivers_today)
    rng.shuffle(candidates)
    candidates.sort(key=lambda d: audit_counts.get(d, 0))
    selected = candidates[:max_daily]
    return selected, {d: "phase_2" for d in selected}


# ─────────────── ORCHESTRATOR ───────────────

async def run_daily_selection(db, client_id: str, target_date: Optional[date] = None) -> dict:
    """Execute the daily selection for a client. Idempotent on re-run for the same date.

    Returns a summary dict with counts for caller / API.
    """
    if target_date is None:
        target_date = _today_cdmx()
    target_dt = _date_to_dt(target_date)

    # STEP 1 — config
    cfg = await db.client_config.find_one({"client_id": client_id, "active": True}, {"_id": 0})
    if not cfg:
        logger.warning(f"[selection] no active client_config for {client_id}")
        return {"ok": False, "error": "no_active_config", "client_id": client_id}
    max_daily = int(cfg["max_daily_audits"])

    # STEP 2 — staged plans for today
    plans = await db.routal_daily_plans.find(
        {"client_id": client_id, "date": target_dt, "processed": False},
        {"_id": 0},
    ).to_list(length=10000)

    if not plans:
        logger.info(f"[selection] no staged plans for {client_id} on {target_date}")
        return {
            "ok": True, "client_id": client_id, "date": str(target_date),
            "total": 0, "selected": 0, "unselected": 0,
            "phase_1": 0, "phase_2": 0, "max_daily_audits": max_daily,
        }

    drivers_today = list({p["driver_id"] for p in plans if p.get("driver_id")})

    # STEP 3 — history
    yesterday_dt = _date_to_dt(target_date - timedelta(days=1))
    audited_yesterday = set()
    cursor_y = db.driver_audit_log.find(
        {"client_id": client_id, "date": yesterday_dt, "selection_status": "selected"},
        {"_id": 0, "driver_id": 1},
    )
    async for doc in cursor_y:
        audited_yesterday.add(doc["driver_id"])

    thirty_days_ago_dt = _date_to_dt(target_date - timedelta(days=30))
    audit_counts: dict = {}
    pipeline = [
        {"$match": {
            "client_id": client_id,
            "date": {"$gte": thirty_days_ago_dt, "$lt": target_dt},
            "selection_status": "selected",
        }},
        {"$group": {"_id": "$driver_id", "count": {"$sum": 1}}},
    ]
    async for doc in db.driver_audit_log.aggregate(pipeline):
        audit_counts[doc["_id"]] = int(doc["count"])

    # STEP 4 — algorithm
    selected_list, phase_map = _select_drivers(
        drivers_today=drivers_today,
        audited_yesterday=audited_yesterday,
        audit_counts=audit_counts,
        max_daily=max_daily,
        target_date=target_date,
    )
    selected_set = set(selected_list)

    # STEP 5 — idempotency: clean previous unselected for this date (re-run safe)
    await db.driver_audit_log.delete_many({
        "client_id": client_id, "date": target_dt, "selection_status": "unselected",
    })

    # Drivers already selected today (don't recreate Journey on re-run)
    already_selected = set()
    cursor_a = db.driver_audit_log.find(
        {"client_id": client_id, "date": target_dt, "selection_status": "selected"},
        {"_id": 0, "driver_id": 1},
    )
    async for doc in cursor_a:
        already_selected.add(doc["driver_id"])
    new_selected = selected_set - already_selected

    # STEP 6 — create Journeys for new selected
    from workers.routal_event_processor import _handle_plan_created_direct  # lazy import

    counts = {"phase_1": 0, "phase_2": 0, "selected_new": 0, "selected_existing": len(already_selected & selected_set)}
    for plan in plans:
        drv = plan.get("driver_id")
        if not drv:
            continue
        if drv in selected_set:
            phase = phase_map.get(drv, "phase_1")
            counts[phase] = counts.get(phase, 0) + 1

            journey_id = None
            if drv in new_selected:
                try:
                    journey_id = await _handle_plan_created_direct(db, plan["route_metadata"], client_id)
                    counts["selected_new"] += 1
                except Exception as e:
                    logger.error(f"[selection] journey create failed for {drv}: {e}")
                    journey_id = None

            await db.driver_audit_log.update_one(
                {"client_id": client_id, "driver_id": drv, "date": target_dt},
                {"$set": {
                    "client_id": client_id,
                    "driver_id": drv,
                    "driver_name": plan.get("driver_name"),
                    "date": target_dt,
                    "plan_id_routal": plan.get("plan_id_routal"),
                    "selection_status": "selected",
                    "selection_phase": phase,
                    "audit_count_30d_at_selection": audit_counts.get(drv, 0),
                    "journey_id": journey_id,
                    "created_at": _now_iso(),
                }},
                upsert=True,
            )
        else:
            # STEP 7 — unselected
            await db.driver_audit_log.update_one(
                {"client_id": client_id, "driver_id": drv, "date": target_dt},
                {"$set": {
                    "client_id": client_id,
                    "driver_id": drv,
                    "driver_name": plan.get("driver_name"),
                    "date": target_dt,
                    "plan_id_routal": plan.get("plan_id_routal"),
                    "selection_status": "unselected",
                    "selection_phase": None,
                    "audit_count_30d_at_selection": audit_counts.get(drv, 0),
                    "journey_id": None,
                    "created_at": _now_iso(),
                }},
                upsert=True,
            )

        # Mark staged plan as processed regardless of branch
        await db.routal_daily_plans.update_one(
            {"client_id": client_id, "driver_id": drv, "date": target_dt},
            {"$set": {"processed": True, "processed_at": _now_iso()}},
        )

    selected_count = len(selected_set)
    unselected_count = len(drivers_today) - selected_count
    if len(drivers_today) > max_daily * 3:
        logger.warning(
            f"[selection] fleet={len(drivers_today)} >3x max_daily={max_daily} for {client_id}; rotation slow"
        )

    summary = {
        "ok": True,
        "client_id": client_id,
        "date": str(target_date),
        "total": len(drivers_today),
        "selected": selected_count,
        "unselected": unselected_count,
        "phase_1": counts["phase_1"],
        "phase_2": counts["phase_2"],
        "max_daily_audits": max_daily,
    }
    logger.info(
        f"[selection] client={client_id} date={target_date} "
        f"selected={selected_count}/{len(drivers_today)} p1={counts['phase_1']} p2={counts['phase_2']}"
    )
    return summary


# ─────────────── SCHEDULER ───────────────

_scheduler_task: Optional[asyncio.Task] = None
_scheduler_stop = asyncio.Event() if False else None  # initialised in start


async def _scheduler_loop(db):
    """Polls every 60s. Triggers run_daily_selection per client when:
       - now (CDMX) >= scheduler_time (HH:MM CDMX),
       - last_scheduled_run_date != today's CDMX date.
    Errors per client are logged but do not stop the loop.
    """
    logger.info("[selection.scheduler] started")
    try:
        while True:
            try:
                now_cdmx = datetime.now(CDMX_TZ)
                today_str = now_cdmx.strftime("%Y-%m-%d")
                cursor = db.client_config.find(
                    {"selection_enabled": True, "active": True},
                    {"_id": 0},
                )
                clients = [c async for c in cursor]
                for cfg in clients:
                    sched = cfg.get("scheduler_time", "06:00")
                    last_run = cfg.get("last_scheduled_run_date")
                    if last_run == today_str:
                        continue  # already ran today
                    try:
                        hh, mm = sched.split(":")
                        target = now_cdmx.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
                    except Exception:
                        logger.warning(f"[selection.scheduler] invalid scheduler_time '{sched}' for {cfg.get('client_id')}")
                        continue
                    if now_cdmx < target:
                        continue
                    cid = cfg["client_id"]
                    try:
                        await run_daily_selection(db, cid)
                        await db.client_config.update_one(
                            {"client_id": cid},
                            {"$set": {"last_scheduled_run_date": today_str, "last_scheduled_run_at": _now_iso()}},
                        )
                        logger.info(f"[selection.scheduler] ran for {cid} on {today_str}")
                    except Exception as e:
                        logger.error(f"[selection.scheduler] error for {cid}: {e}")
            except Exception as e:
                logger.error(f"[selection.scheduler] tick error: {e}")
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        logger.info("[selection.scheduler] cancelled")
        raise


def start_selection_scheduler(db):
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        return
    _scheduler_task = asyncio.create_task(_scheduler_loop(db))


def stop_selection_scheduler():
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
