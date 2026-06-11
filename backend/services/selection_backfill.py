"""
Selection plan backfill service — fallback when Routal webhooks are not arriving.

Why this exists:
The selection scheduler depends on `routal_daily_plans` being pre-populated by
Routal webhooks (`plan.created`, `plan.updated`). If webhooks stop arriving (e.g.
because the client's Routal webhook URL was misconfigured, the webhook secret
rotated, or Routal delayed sending), the scheduler tick finds 0 staged plans and
selects 0 drivers — even though Routal has plans for today.

This module provides `backfill_plans_for_date()` which fetches plans directly
from the Routal API for a given date and stages them into `routal_daily_plans`,
making the system resilient to webhook outages.

Used by:
  - routal_selection_worker._scheduler_loop (auto-fallback before selection)
  - routes.selection_routes (manual "Recuperar rango" button — eventually)
"""
from __future__ import annotations
import logging
from datetime import datetime, date, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
MAX_PAGES = 30          # tighter than the manual endpoint (50) — auto runs more frequently
MAX_HYDRATE = 200       # soft cap


async def backfill_plans_for_date(db, client_id: str, target_date: date) -> dict:
    """Hydrate `routal_daily_plans` for a single date directly from Routal API.

    Idempotent (uses upsert by client_id+driver_id+date).

    Returns dict with `ok`, `staged`, `error` (optional).
    Returns `ok=True, staged=0` quietly if Routal integration is inactive — the
    caller decides what to do (e.g. proceed with empty staging).
    """
    from services.integration_service import IntegrationService
    svc = IntegrationService(db)
    rc = await svc.get_routal_client(client_id)
    if not rc:
        return {"ok": True, "staged": 0, "error": "routal_inactive"}

    df_dt = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
    dt_dt_excl = df_dt + timedelta(days=1)

    pages_scanned = 0
    plans_scanned = 0
    in_range_plans: list = []
    consecutive_below = 0

    try:
        for page in range(MAX_PAGES):
            try:
                data = await rc._request("GET", "/v2/plans", params={"limit": PAGE_SIZE, "offset": page * PAGE_SIZE})
            except Exception as e:
                logger.error(f"[selection.auto-backfill] list_plans error client={client_id} page={page}: {e}")
                return {"ok": False, "staged": 0, "error": f"routal_api: {str(e)[:200]}"}
            plans = data if isinstance(data, list) else (data.get("docs") or data.get("data") or data.get("plans") or [])
            if not plans:
                break
            pages_scanned += 1
            plans_scanned += len(plans)
            page_below = 0
            for p in plans:
                exd = p.get("execution_date")
                if not exd:
                    continue
                try:
                    pdt = datetime.fromisoformat(str(exd).replace("Z", "+00:00"))
                except Exception:
                    continue
                if pdt < df_dt:
                    page_below += 1
                    continue
                if pdt >= dt_dt_excl:
                    continue
                in_range_plans.append(p)
                if len(in_range_plans) >= MAX_HYDRATE:
                    break
            if len(in_range_plans) >= MAX_HYDRATE:
                break
            # Routal returns plans newest-first → bail when whole pages are below range
            if page_below >= len(plans) * 0.9:
                consecutive_below += 1
                if consecutive_below >= 2:
                    break
            else:
                consecutive_below = 0
            if len(plans) < PAGE_SIZE:
                break

        # Hydrate each in-range plan (one staged row per real route)
        staged = 0
        skipped = 0
        for p in in_range_plans:
            plan_id = p.get("id") or p.get("plan_id")
            if not plan_id:
                continue
            try:
                detail = await rc.get_plan(plan_id)
            except Exception as e:
                logger.warning(f"[selection.auto-backfill] get_plan {plan_id} failed: {e}")
                skipped += 1
                continue
            exd = p.get("execution_date") or detail.get("execution_date")
            try:
                pdt = datetime.fromisoformat(str(exd).replace("Z", "+00:00"))
                plan_date = datetime(pdt.year, pdt.month, pdt.day, tzinfo=timezone.utc)
                date_str = plan_date.strftime("%Y-%m-%d")
            except Exception:
                skipped += 1
                continue
            stops = detail.get("stops") or []
            routes = detail.get("routes") or detail.get("drivers") or []
            if not routes:
                continue
            plan_label = detail.get("label") or p.get("label")
            project_id = detail.get("project_id") or p.get("project_id") or detail.get("organization_id")
            for route in routes:
                drv_id = route.get("id") or route.get("external_id")
                drv_name = route.get("label") or "Sin asignar"
                if not drv_id:
                    continue
                if str(drv_name).startswith("LastmileScanSessions"):
                    continue
                route_stops = [s for s in stops if s.get("route_id") == drv_id]
                # Bug fix 2026-05-06: skip routes with no packages. Matches user
                # request "solo contemple rutas que contengan paquetes" — empty
                # routes pollute /journeys and waste audit slots.
                if not route_stops:
                    continue
                payload = {
                    "id": plan_id,
                    "plan_id": plan_id,
                    "label": plan_label,
                    "project_id": project_id,
                    "execution_date": exd,
                    "date": date_str,
                    # RTV2 (2026-06-11): persist Routal `status` so the package-cohort
                    # selector can filter by operational state (in_progress / planning / completed).
                    # Without this, `classify_plan_operational_state` defaults to "created" and
                    # the knapsack filters out every plan → 0 selected (the prod bug we're fixing).
                    "status": detail.get("status") or p.get("status"),
                    "driver": {"id": drv_id, "name": drv_name},
                    "driver_id": drv_id,
                    "driver_name": drv_name,
                    "stops": route_stops,
                    "services": route_stops,
                    "_backfilled": True,
                    "_backfilled_at": datetime.now(timezone.utc).isoformat(),
                    "_backfill_source": "auto_scheduler",
                }
                await db.routal_daily_plans.update_one(
                    {"client_id": client_id, "driver_id": drv_id, "date": plan_date},
                    {"$set": {
                        "client_id": client_id,
                        "driver_id": drv_id,
                        "driver_name": drv_name,
                        "date": plan_date,
                        "plan_id_routal": plan_id,
                        "routal_route_id": drv_id,
                        "route_metadata": payload,
                        "received_at": datetime.now(timezone.utc).isoformat(),
                        "processed": False,
                        "source": "auto_backfill",
                    }},
                    upsert=True,
                )
                staged += 1

        return {"ok": True, "staged": staged, "pages_scanned": pages_scanned, "plans_scanned": plans_scanned}
    finally:
        try:
            await rc.aclose()
        except Exception:
            pass


async def maybe_backfill_if_empty(db, client_id: str, target_date: date, force_refresh: bool = False) -> Optional[dict]:
    """Run backfill ONLY if there are no unprocessed staged plans for this client/date.

    Args:
        force_refresh: when True, ALWAYS hit the Routal API and re-upsert (refreshes
            `status` and resets `processed=False`). Used at scheduler cutoff time
            so the cohort selector always sees the LIVE Routal status — without
            this, plans staged via webhook at status="created" stay "created" in
            our DB forever and never become eligible for the in_progress filter.

    Returns the backfill result dict, or None if no backfill was needed.
    """
    if not force_refresh:
        target_dt = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
        pending = await db.routal_daily_plans.count_documents(
            {"client_id": client_id, "date": target_dt, "processed": False}
        )
        if pending > 0:
            return None  # webhooks delivered plans — no need to backfill
        logger.info(
            f"[selection.auto-backfill] client={client_id} date={target_date} no staged plans, "
            f"pulling from Routal API…"
        )
    else:
        logger.info(
            f"[selection.auto-backfill] client={client_id} date={target_date} force_refresh=True, "
            f"refreshing live status from Routal API…"
        )
    result = await backfill_plans_for_date(db, client_id, target_date)
    if result.get("staged", 0) > 0:
        logger.info(
            f"[selection.auto-backfill] client={client_id} date={target_date} "
            f"staged={result['staged']} (force_refresh={force_refresh})"
        )
    elif result.get("error") and result["error"] != "routal_inactive":
        logger.warning(
            f"[selection.auto-backfill] client={client_id} backfill error: {result['error']}"
        )
    return result
