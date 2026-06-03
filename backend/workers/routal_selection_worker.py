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


# ─────────────── RTV2: PACKAGE-ORIENTED COHORT (2026-05-30) ───────────────

def _is_scanner_placeholder_safe(label) -> bool:
    """Mirror of workers.routal_event_processor._is_scanner_placeholder without
    importing it (avoid cycles). Filters out depot/placeholder stops that should
    not count as a real package for cohort decisions."""
    if not label or not isinstance(label, str):
        return False
    s = label.strip().lower()
    return s.startswith("scanner ") or s in ("depot", "warehouse", "almacen")


def classify_plan_operational_state(plan: dict, eligibility_states: list) -> str:
    """Classifies a Routal plan into 'in_progress' / 'created' / 'completed' / 'cancelled'
    based on Routal's plan.status. Returns the literal Routal status.

    The caller decides eligibility comparing against `eligibility_states`.
    Defaults strictly: only plans with status='in_progress' are auditable.
    """
    status = (plan.get("routal_status") or plan.get("status") or "").strip().lower()
    if status in ("in_progress", "started", "running"):
        return "in_progress"
    if status in ("completed", "finished", "done", "closed"):
        return "completed"
    if status in ("cancelled", "canceled", "deleted"):
        return "cancelled"
    return "created"


def _calendar_week_bounds(target_date: date) -> tuple[date, date]:
    """Returns (monday, sunday) of the calendar week containing target_date (Mon=0)."""
    monday = target_date - timedelta(days=target_date.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


async def compute_adjusted_target_packages(
    db, client_id: str, target_date: date, cfg: dict
) -> dict:
    """RTV2: adaptive_calendar_week target computation.

    Returns:
        {
            "strategy": "flat" | "adaptive_calendar_week",
            "target_daily": int,           # base daily target from config
            "min_daily": int,
            "max_daily": int,
            "adjusted_target": int,        # value to use in knapsack
            "week_monday": "YYYY-MM-DD",
            "week_sunday": "YYYY-MM-DD",
            "week_accumulated": int,       # packages audited Mon..yesterday
            "week_target": int,
            "days_remaining_incl_today": int,
        }
    """
    target_base = int(cfg.get("audit_target_packages_daily", 1000))
    min_p = int(cfg.get("audit_min_packages_daily", 800))
    max_p = int(cfg.get("audit_max_packages_daily", 1200))
    weekly_target = int(cfg.get("audit_target_packages_weekly", 7000))
    strategy = cfg.get("audit_distribution_strategy", "adaptive_calendar_week")

    monday, sunday = _calendar_week_bounds(target_date)
    days_remaining = (sunday - target_date).days + 1  # includes today

    result = {
        "strategy": strategy,
        "target_daily": target_base,
        "min_daily": min_p,
        "max_daily": max_p,
        "week_monday": monday.isoformat(),
        "week_sunday": sunday.isoformat(),
        "week_target": weekly_target,
        "days_remaining_incl_today": days_remaining,
        "week_accumulated": 0,
        "adjusted_target": target_base,
    }

    if strategy == "flat":
        return result

    # adaptive_calendar_week: compute accumulated Mon..yesterday
    if target_date > monday:
        monday_dt = _date_to_dt(monday)
        today_dt = _date_to_dt(target_date)
        pipeline = [
            {"$match": {
                "client_id": client_id,
                "selection_status": "selected",
                "date": {"$gte": monday_dt, "$lt": today_dt},
            }},
            {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$packages_audited", 0]}}}},
        ]
        accumulated = 0
        async for doc in db.driver_audit_log.aggregate(pipeline):
            accumulated = int(doc.get("total") or 0)
        result["week_accumulated"] = accumulated

    target_residual = weekly_target - result["week_accumulated"]
    if days_remaining <= 0:
        adjusted = min_p
    else:
        adjusted = target_residual / days_remaining
    # Clamp to band
    adjusted_int = max(min_p, min(max_p, int(round(adjusted))))
    result["adjusted_target"] = adjusted_int
    return result


def knapsack_select_by_packages(
    ordered_plans: list,
    adjusted_target: int,
    max_packages: int,
    overshoot_tolerance: float = 0.10,
) -> tuple[list, list, dict]:
    """RTV2: greedy selection by packages.

    Iterates `ordered_plans` (already sorted by phase_1 → phase_2 priority) and
    accumulates until adjusted_target ± tolerance is reached, never exceeding
    max_packages × (1 + tolerance).

    Each plan dict must have at minimum: id, driver_id, packages_count.
    Returns (selected, discarded, summary).
    """
    selected: list = []
    discarded: list = []
    acc = 0
    hard_ceiling = int(max_packages * (1 + overshoot_tolerance))
    soft_ceiling = int(adjusted_target * (1 + overshoot_tolerance))
    discard_reason_summary: dict = {}

    for plan in ordered_plans:
        pkgs = int(plan.get("packages_count") or 0)
        if pkgs <= 0:
            discarded.append({**plan, "_discard_reason": "no_packages"})
            discard_reason_summary["no_packages"] = discard_reason_summary.get("no_packages", 0) + 1
            continue

        projected = acc + pkgs
        # Hard cap: never exceed max × tolerance
        if projected > hard_ceiling:
            discarded.append({**plan, "_discard_reason": "hard_cap_reached"})
            discard_reason_summary["hard_cap_reached"] = discard_reason_summary.get("hard_cap_reached", 0) + 1
            continue
        # Soft cap: if target reached with margin, stop accumulating (don't blow target by 100%)
        if acc >= adjusted_target and projected > soft_ceiling:
            discarded.append({**plan, "_discard_reason": "target_reached_with_margin"})
            discard_reason_summary["target_reached_with_margin"] = discard_reason_summary.get("target_reached_with_margin", 0) + 1
            continue

        selected.append(plan)
        acc += pkgs

    summary = {
        "selected_count": len(selected),
        "selected_packages": acc,
        "discarded_count": len(discarded),
        "discard_reasons": discard_reason_summary,
        "adjusted_target": adjusted_target,
        "hard_ceiling": hard_ceiling,
        "soft_ceiling": soft_ceiling,
    }
    return selected, discarded, summary


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
    # max_daily is computed inside legacy branch (STEP 6) — package mode uses
    # the new audit_max_packages_daily / audit_target_packages_daily band.
    max_daily = int(cfg.get("max_daily_audits", 30))

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

    # STEP 4 — historial: drivers already selected today (re-run safe).
    # We read this BEFORE running the algorithm so we can compute the remaining
    # quota and only consider new candidates. This makes the function additive:
    # subsequent backfills (manual or auto) can fill up to max_daily without
    # re-electing or excessively double-counting drivers selected earlier.
    already_selected = set()
    already_phase_map: dict = {}
    cursor_a = db.driver_audit_log.find(
        {"client_id": client_id, "date": target_dt, "selection_status": "selected"},
        {"_id": 0, "driver_id": 1, "selection_phase": 1},
    )
    async for doc in cursor_a:
        already_selected.add(doc["driver_id"])
        already_phase_map[doc["driver_id"]] = doc.get("selection_phase") or "phase_1"

    # STEP 5 — idempotency: clean previous unselected for this date so newly
    # arrived drivers can be re-evaluated against the remaining quota.
    await db.driver_audit_log.delete_many({
        "client_id": client_id, "date": target_dt, "selection_status": "unselected",
    })

    # STEP 6 — algorithm on REMAINING quota.
    #
    # RTV2 (2026-05-30): bifurcación según estrategia configurada.
    # ───────────────────────────────────────────────────────────────
    # Si el cliente tiene `audit_target_packages_daily` configurado (cohort
    # orientado a paquetes), aplicamos:
    #   1. Filtro de elegibilidad por estado operativo (default: only in_progress)
    #   2. Ordenamiento phase_1 (drivers no auditados ayer) → phase_2
    #   3. Knapsack greedy por paquetes hasta adjusted_target
    # Caso contrario: cae al algoritmo legacy `_select_drivers` (rotación por route count).
    #
    # Bug fix 2026-05-06 (legacy path preserved): max_daily route count se aplica
    # como hard cap absoluto si está configurado.
    target_packages_daily = cfg.get("audit_target_packages_daily")
    package_mode = bool(target_packages_daily) and bool(cfg.get("audit_distribution_strategy"))

    candidate_drivers = [d for d in drivers_today if d not in already_selected]

    if package_mode:
        # ───── PACKAGE-ORIENTED COHORT ─────
        cohort_info = await compute_adjusted_target_packages(db, client_id, target_date, cfg)
        adjusted_target = cohort_info["adjusted_target"]
        max_pkg_daily = int(cfg.get("audit_max_packages_daily", 1200))
        tolerance = float(cfg.get("audit_overshoot_tolerance", 0.10))
        eligibility_states = set(cfg.get("ingest_eligibility_states", ["in_progress"]))

        # Filter plans by operational state + new drivers only
        eligible_plans = []
        for p in plans:
            if p.get("driver_id") in already_selected:
                continue
            op_state = classify_plan_operational_state(p.get("route_metadata") or {}, list(eligibility_states))
            if op_state not in eligibility_states:
                continue
            # Compute packages_count from route_metadata stops/services
            rm = p.get("route_metadata") or {}
            stops = rm.get("stops") or rm.get("services") or []
            pkgs_count = sum(
                1 for s in stops
                if not _is_scanner_placeholder_safe(s.get("label") if isinstance(s, dict) else None)
            ) if stops else int(p.get("packages_count") or 0)
            eligible_plans.append({
                **p,
                "packages_count": pkgs_count,
                "_op_state": op_state,
            })

        # Order plans by driver phase: phase_1 (not audited yesterday) first
        rng = random.Random(_seed_for_date(target_date))
        phase_1_plans = [p for p in eligible_plans if p["driver_id"] not in audited_yesterday]
        phase_2_plans = [p for p in eligible_plans if p["driver_id"] in audited_yesterday]
        rng.shuffle(phase_1_plans)
        phase_2_plans.sort(key=lambda p: audit_counts.get(p["driver_id"], 0))
        ordered_plans = phase_1_plans + phase_2_plans

        selected_plans, discarded_plans, ks_summary = knapsack_select_by_packages(
            ordered_plans, adjusted_target, max_pkg_daily, overshoot_tolerance=tolerance
        )

        selected_list = [p["driver_id"] for p in selected_plans]
        phase_map = {
            p["driver_id"]: ("phase_1" if p["driver_id"] not in audited_yesterday else "phase_2")
            for p in selected_plans
        }

        # Persist cohort decision for /api/captacion/stats endpoint
        await db.selection_runs.insert_one({
            "client_id": client_id,
            "date": target_dt,
            "ran_at": _now_iso(),
            "mode": "package",
            "cohort": cohort_info,
            "knapsack": ks_summary,
            "eligible_count": len(eligible_plans),
            "selected_count": len(selected_plans),
            "discarded_count": len(discarded_plans),
        })
        logger.info(
            f"[selection.pkg] client={client_id} date={target_date} "
            f"eligible={len(eligible_plans)} selected={len(selected_plans)} "
            f"pkgs={ks_summary['selected_packages']}/{adjusted_target} "
            f"discarded={len(discarded_plans)} reasons={ks_summary['discard_reasons']}"
        )
    else:
        # ───── LEGACY ROUTE-COUNT COHORT ─────
        max_daily = int(cfg.get("max_daily_audits", 30))
        remaining_quota = max(0, max_daily - len(already_selected))
        if remaining_quota > 0 and candidate_drivers:
            selected_list, phase_map = _select_drivers(
                drivers_today=candidate_drivers,
                audited_yesterday=audited_yesterday,
                audit_counts=audit_counts,
                max_daily=remaining_quota,
                target_date=target_date,
            )
        else:
            selected_list, phase_map = [], {}

    new_selected = set(selected_list)
    # Combined view for summary metrics (already + new) — never re-elect existing
    selected_set = already_selected | new_selected

    # STEP 7 — create Journeys for new selected; do NOT touch audit_log entries
    # of drivers already selected (preserves their original phase / journey_id).
    from workers.routal_event_processor import _handle_plan_created_direct  # lazy import

    counts = {
        "phase_1": sum(1 for d in already_selected if already_phase_map.get(d) == "phase_1"),
        "phase_2": sum(1 for d in already_selected if already_phase_map.get(d) == "phase_2"),
        "selected_new": 0,
        "selected_existing": len(already_selected),
    }
    for plan in plans:
        drv = plan.get("driver_id")
        if not drv:
            continue
        plan_branch_id = plan.get("branch_id")

        # Already selected earlier today: don't overwrite the audit log entry
        # (preserves the original phase + journey_id). Just mark plan processed.
        if drv in already_selected:
            await db.routal_daily_plans.update_one(
                {"client_id": client_id, "driver_id": drv, "date": target_dt},
                {"$set": {"processed": True, "processed_at": _now_iso()}},
            )
            continue

        if drv in new_selected:
            phase = phase_map.get(drv, "phase_1")
            counts[phase] = counts.get(phase, 0) + 1

            journey_id = None
            try:
                journey_id = await _handle_plan_created_direct(
                    db, plan["route_metadata"], client_id, branch_id=plan_branch_id,
                )
                counts["selected_new"] += 1
            except Exception as e:
                logger.error(f"[selection] journey create failed for {drv}: {e}")
                journey_id = None

            # Compute packages_audited for this driver's plan (RTV2: weekly target accumulator)
            rm = plan.get("route_metadata") or {}
            _stops = rm.get("stops") or rm.get("services") or []
            pkgs_audited = sum(
                1 for s in _stops
                if isinstance(s, dict) and not _is_scanner_placeholder_safe(s.get("label"))
            ) if _stops else int(plan.get("packages_count") or 0)

            await db.driver_audit_log.update_one(
                {"client_id": client_id, "driver_id": drv, "date": target_dt},
                {"$set": {
                    "client_id": client_id,
                    "branch_id": plan_branch_id,
                    "driver_id": drv,
                    "driver_name": plan.get("driver_name"),
                    "date": target_dt,
                    "plan_id_routal": plan.get("plan_id_routal"),
                    "selection_status": "selected",
                    "selection_phase": phase,
                    "audit_count_30d_at_selection": audit_counts.get(drv, 0),
                    "journey_id": journey_id,
                    "packages_audited": pkgs_audited,
                    "created_at": _now_iso(),
                }},
                upsert=True,
            )
        else:
            # STEP 8 — unselected
            await db.driver_audit_log.update_one(
                {"client_id": client_id, "driver_id": drv, "date": target_dt},
                {"$set": {
                    "client_id": client_id,
                    "branch_id": plan_branch_id,
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

    # RT-09: per-branch breakdown for multi-project clients (Cubbo CDMX/GDL/...)
    branch_breakdown = {}
    for plan in plans:
        bid = plan.get("branch_id")
        if not bid:
            continue
        bb = branch_breakdown.setdefault(bid, {"total": 0, "selected": 0})
        bb["total"] += 1
        if plan.get("driver_id") in selected_set:
            bb["selected"] += 1
    # Resolve branch_id → code for human-readable summary
    if branch_breakdown:
        branch_codes = {}
        async for b in db.branches.find(
            {"id": {"$in": list(branch_breakdown.keys())}},
            {"_id": 0, "id": 1, "code": 1},
        ):
            branch_codes[b["id"]] = b["code"]
        branch_breakdown_named = {
            branch_codes.get(bid, bid[:8]): vals for bid, vals in branch_breakdown.items()
        }
    else:
        branch_breakdown_named = {}

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
        "branch_breakdown": branch_breakdown_named,
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
       - now (CDMX) >= any of the configured cutoff times (scheduler_times[]),
       - that specific cutoff hasn't fired today (last_scheduled_run_dates[time] != today).

    RT-11: supports multiple cutoff times per day (e.g. ["06:00", "12:00", "18:00"])
    so that selection re-runs throughout the day to capture late-arriving Routal plans.
    Each cutoff is tracked independently in `last_scheduled_run_dates` (dict).

    Legacy single `scheduler_time` field is honored for back-compat.
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
                    times = cfg.get("scheduler_times")
                    if not times or not isinstance(times, list):
                        # Fallback to legacy single-time
                        single = cfg.get("scheduler_time", "06:00")
                        times = [single]
                    # RTV2 (2026-05-30): include ingest_cutoff_time as a scheduler cutoff
                    # so the package-oriented cohort selection runs at the configured hour
                    # (default 16:00 CDMX). Idempotent: tracked in last_scheduled_run_dates.
                    cutoff = cfg.get("ingest_cutoff_time")
                    if cutoff and cutoff not in times:
                        times = list(times) + [cutoff]
                    last_runs = cfg.get("last_scheduled_run_dates") or {}
                    # Legacy compatibility: if old `last_scheduled_run_date` exists, treat
                    # it as "first cutoff already ran today"
                    legacy_last = cfg.get("last_scheduled_run_date")
                    if legacy_last == today_str and times and times[0] not in last_runs:
                        last_runs[times[0]] = today_str

                    cid = cfg["client_id"]
                    for sched in times:
                        if last_runs.get(sched) == today_str:
                            continue  # this cutoff already fired today
                        try:
                            hh, mm = sched.split(":")
                            target = now_cdmx.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
                        except Exception:
                            logger.warning(f"[selection.scheduler] invalid scheduler_time '{sched}' for {cid}")
                            continue
                        if now_cdmx < target:
                            continue
                        try:
                            # Bug fix 2026-05-06: auto-backfill from Routal API when
                            # webhooks haven't delivered plans. Cubbo MX hadn't
                            # received a webhook in 10 days but scheduler kept firing
                            # with empty staging → 0 selected. This makes the scheduler
                            # resilient to webhook outages.
                            from services.selection_backfill import maybe_backfill_if_empty
                            try:
                                bf = await maybe_backfill_if_empty(db, cid, now_cdmx.date())
                                if bf and bf.get("staged", 0) > 0:
                                    logger.info(
                                        f"[selection.scheduler] auto-backfilled {bf['staged']} plans "
                                        f"for {cid} cutoff={sched} (webhooks gap)"
                                    )
                            except Exception as bfe:
                                logger.warning(
                                    f"[selection.scheduler] backfill failed for {cid} cutoff={sched}: {bfe}"
                                )
                            await run_daily_selection(db, cid)
                            last_runs[sched] = today_str
                            await db.client_config.update_one(
                                {"client_id": cid},
                                {"$set": {
                                    "last_scheduled_run_dates": last_runs,
                                    "last_scheduled_run_date": today_str,  # legacy field
                                    "last_scheduled_run_at": _now_iso(),
                                }},
                            )
                            logger.info(f"[selection.scheduler] ran for {cid} cutoff={sched} on {today_str}")
                        except Exception as e:
                            logger.error(f"[selection.scheduler] error for {cid} cutoff={sched}: {e}")
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
