"""
Selection module endpoints (R00B / SEL01).

  POST   /api/selection/run/{client_id}        (developer | coordinator)
  GET    /api/selection/summary/{client_id}    (developer | coordinator | executive)
  GET    /api/drivers/audit-history/{driver_id}?client_id=…   (developer | coordinator)
  GET    /api/client-config                    (developer)            ← list all
  GET    /api/client-config/{client_id}        (developer)
  PATCH  /api/client-config/{client_id}        (developer)

All endpoints require client_id scoping.
"""
import logging
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from zoneinfo import ZoneInfo

from dependencies import get_current_user, db
from services.client_config_service import ClientConfigService
from workers.routal_selection_worker import run_daily_selection, _date_to_dt

logger = logging.getLogger(__name__)
router = APIRouter(tags=["selection"])
CDMX_TZ = ZoneInfo("America/Mexico_City")


def _require_role(user: dict, roles: list[str]):
    if user.get("role") not in roles:
        raise HTTPException(status_code=403, detail=f"Solo {', '.join(roles)} pueden acceder")


def _parse_date(s: Optional[str]) -> date:
    if not s:
        return datetime.now(CDMX_TZ).date()
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="date debe tener formato YYYY-MM-DD")


# ─────────────── SELECTION ───────────────

@router.post("/selection/run/{client_id}")
async def run_selection(
    client_id: str,
    date: Optional[str] = Query(None, description="YYYY-MM-DD; default = hoy CDMX"),
    user: dict = Depends(get_current_user),
):
    _require_role(user, ["developer", "coordinator"])
    target = _parse_date(date)

    cfg = await db.client_config.find_one({"client_id": client_id}, {"_id": 0})
    if not cfg:
        raise HTTPException(
            status_code=400,
            detail=(
                "Este cliente no tiene configuración SEL01. Ve a Settings → Auditorías, "
                "selecciona el cliente, activa el switch 'Selección habilitada' y guarda. "
                "Luego intenta de nuevo."
            ),
        )
    if not cfg.get("selection_enabled"):
        raise HTTPException(
            status_code=400,
            detail=f"El cliente '{cfg.get('client_name', client_id)}' tiene selección desactivada (auto-crear legacy). Activa 'Selección habilitada' primero.",
        )
    if not cfg.get("active", True):
        raise HTTPException(status_code=400, detail="Cliente marcado inactivo en client_config.")

    summary = await run_daily_selection(db, client_id, target_date=target)
    if not summary.get("ok"):
        raise HTTPException(status_code=400, detail=summary.get("error", "selection failed"))
    return summary


@router.post("/selection/run-range/{client_id}")
async def run_selection_range(
    client_id: str,
    date_from: str = Query(..., description="YYYY-MM-DD inicio del rango (inclusivo)"),
    date_to: str = Query(..., description="YYYY-MM-DD fin del rango (inclusivo)"),
    user: dict = Depends(get_current_user),
):
    """Ejecuta el algoritmo de selección día por día sobre un rango de fechas.

    IMPORTANTE: solo procesa planes que ya están staged en `routal_daily_plans`,
    es decir, planes que llegaron vía webhook Routal `plan.created` cuando
    `selection_enabled=true` estaba activo. NO re-procesa journeys creados
    directamente por Cosmo o Manual.
    """
    _require_role(user, ["developer", "coordinator"])

    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    if df > dt:
        raise HTTPException(status_code=400, detail="date_from debe ser ≤ date_to")
    delta_days = (dt - df).days + 1
    if delta_days > 90:
        raise HTTPException(status_code=400, detail=f"Rango demasiado grande ({delta_days} días). Máximo 90.")

    cfg = await db.client_config.find_one({"client_id": client_id}, {"_id": 0})
    if not cfg:
        raise HTTPException(
            status_code=400,
            detail=(
                "Este cliente no tiene configuración SEL01. Ve a Settings → Auditorías, "
                "selecciona el cliente, activa el switch 'Selección habilitada' y guarda. "
                "Luego intenta de nuevo."
            ),
        )
    if not cfg.get("selection_enabled"):
        raise HTTPException(
            status_code=400,
            detail=f"El cliente '{cfg.get('client_name', client_id)}' tiene selección desactivada (auto-crear legacy). Activa 'Selección habilitada' primero.",
        )
    if not cfg.get("active", True):
        raise HTTPException(status_code=400, detail="Cliente marcado inactivo en client_config.")

    from datetime import timedelta as _td
    daily_results = []
    totals = {"total": 0, "selected": 0, "unselected": 0, "phase_1": 0, "phase_2": 0, "days_processed": 0, "days_with_data": 0}
    cur = df
    while cur <= dt:
        try:
            s = await run_daily_selection(db, client_id, target_date=cur)
            daily_results.append({
                "date": str(cur),
                "ok": s.get("ok"),
                "total": s.get("total", 0),
                "selected": s.get("selected", 0),
                "unselected": s.get("unselected", 0),
                "phase_1": s.get("phase_1", 0),
                "phase_2": s.get("phase_2", 0),
                "error": s.get("error"),
            })
            if s.get("ok"):
                totals["days_processed"] += 1
                if s.get("total", 0) > 0:
                    totals["days_with_data"] += 1
                totals["total"] += s.get("total", 0)
                totals["selected"] += s.get("selected", 0)
                totals["unselected"] += s.get("unselected", 0)
                totals["phase_1"] += s.get("phase_1", 0)
                totals["phase_2"] += s.get("phase_2", 0)
        except Exception as e:
            logger.error(f"[selection.run-range] error día {cur}: {e}")
            daily_results.append({"date": str(cur), "ok": False, "error": str(e)[:200]})
        cur = cur + _td(days=1)

    return {
        "client_id": client_id,
        "date_from": str(df),
        "date_to": str(dt),
        "days_in_range": delta_days,
        **totals,
        "results": daily_results,
    }


@router.post("/selection/backfill-from-routal/{client_id}")
async def backfill_from_routal(
    client_id: str,
    date_from: str = Query(..., description="YYYY-MM-DD inicio (inclusivo)"),
    date_to: str = Query(..., description="YYYY-MM-DD fin (inclusivo)"),
    auto_run_selection: bool = Query(True, description="Ejecutar algoritmo SEL01 día por día tras el backfill"),
    user: dict = Depends(get_current_user),
):
    """Hidrata `routal_daily_plans` consultando `GET /v2/plans` de Routal con paginación
    y filtrando por execution_date dentro del rango. Útil cuando el usuario activó
    `selection_enabled=true` recientemente y quiere recuperar planes históricos sin
    esperar a que Routal reenvíe webhooks. Idempotente: usa upsert por (client_id, driver_id, date).

    Caps de seguridad:
      - Rango máximo 90 días.
      - Máximo 50 páginas escaneadas (5000 plans).
      - Máximo 200 plans hidratados por llamada (re-ejecuta con rangos más cortos si tu flota es grande).
    """
    _require_role(user, ["developer"])

    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    if df > dt:
        raise HTTPException(status_code=400, detail="date_from debe ser ≤ date_to")
    if (dt - df).days + 1 > 90:
        raise HTTPException(status_code=400, detail="Rango máximo 90 días")

    cfg = await db.client_config.find_one({"client_id": client_id}, {"_id": 0})
    if not cfg:
        raise HTTPException(
            status_code=400,
            detail=(
                "Este cliente no tiene configuración SEL01. Ve a Settings → Auditorías, "
                "selecciona el cliente, activa el switch 'Selección habilitada' y guarda."
            ),
        )
    if not cfg.get("selection_enabled"):
        raise HTTPException(
            status_code=400,
            detail=f"El cliente '{cfg.get('client_name', client_id)}' tiene selección desactivada. Actívala primero.",
        )

    from services.integration_service import IntegrationService
    svc = IntegrationService(db)
    rc = await svc.get_routal_client(client_id)
    if not rc:
        raise HTTPException(
            status_code=400,
            detail="La integración Routal no está activa para este cliente o faltan credenciales (API key).",
        )

    df_dt = datetime(df.year, df.month, df.day, tzinfo=timezone.utc)
    dt_dt_excl = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc) + timedelta(days=1)

    PAGE_SIZE = 100
    MAX_PAGES = 50
    MAX_HYDRATE = 200

    pages_scanned = 0
    plans_scanned = 0
    in_range_plans = []
    consecutive_below = 0

    try:
        for page in range(MAX_PAGES):
            try:
                data = await rc._request("GET", "/v2/plans", params={"limit": PAGE_SIZE, "offset": page * PAGE_SIZE})
            except Exception as e:
                logger.error(f"[backfill] list_plans error page={page}: {e}")
                raise HTTPException(status_code=502, detail=f"Error consultando Routal: {str(e)[:200]}")
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
                logger.warning(f"[backfill] reached MAX_HYDRATE={MAX_HYDRATE}; truncating")
                break
            # Routal returns plans newest-first → si toda la página está bajo el rango, terminamos
            if page_below >= len(plans) * 0.9:
                consecutive_below += 1
                if consecutive_below >= 2:
                    break
            else:
                consecutive_below = 0
            if len(plans) < PAGE_SIZE:
                break

        # Hydrate each in-range plan
        staged = 0
        skipped_no_driver = 0
        skipped_error = 0
        for p in in_range_plans:
            plan_id = p.get("id") or p.get("plan_id")
            if not plan_id:
                skipped_error += 1
                continue
            try:
                detail = await rc.get_plan(plan_id)
            except Exception as e:
                logger.warning(f"[backfill] get_plan {plan_id} failed: {e}")
                skipped_error += 1
                continue
            exd = p.get("execution_date") or detail.get("execution_date")
            try:
                pdt = datetime.fromisoformat(str(exd).replace("Z", "+00:00"))
                plan_date = datetime(pdt.year, pdt.month, pdt.day, tzinfo=timezone.utc)
                date_str = plan_date.strftime("%Y-%m-%d")
            except Exception:
                skipped_error += 1
                continue
            stops = detail.get("stops") or []
            routes = detail.get("routes") or detail.get("drivers") or []
            if not routes:
                skipped_no_driver += 1
                continue
            plan_label = detail.get("label") or p.get("label")
            project_id = detail.get("project_id") or p.get("project_id") or detail.get("organization_id")
            for route in routes:
                drv_id = route.get("id") or route.get("external_id")
                drv_name = route.get("label") or "Sin asignar"
                if not drv_id:
                    skipped_no_driver += 1
                    continue
                # Skip scanner placeholders (route auto-named when no driver assigned yet)
                if str(drv_name).startswith("LastmileScanSessions"):
                    skipped_no_driver += 1
                    continue
                # Filter stops to only the ones assigned to THIS route
                route_stops = [s for s in stops if s.get("route_id") == drv_id]
                # Bug fix 2026-05-06: skip routes with no packages. Empty shells
                # pollute /journeys and waste audit slots. Matches the auto-backfill
                # behavior in services/selection_backfill.py.
                if not route_stops:
                    skipped_no_driver += 1
                    continue
                payload = {
                    "id": plan_id,
                    "plan_id": plan_id,
                    "label": plan_label,
                    "project_id": project_id,
                    "execution_date": exd,
                    "date": date_str,
                    # RTV2 (2026-06-11): persist Routal `status` so the package-cohort
                    # selector can filter by operational state. See selection_backfill.py.
                    "status": detail.get("status") or p.get("status"),
                    "driver": {"id": drv_id, "name": drv_name},
                    "driver_id": drv_id,
                    "driver_name": drv_name,
                    "stops": route_stops,
                    "services": route_stops,
                    "_backfilled": True,
                    "_backfilled_at": datetime.now(timezone.utc).isoformat(),
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
                        "source": "backfill",
                    }},
                    upsert=True,
                )
                staged += 1

        # Run selection per day in range
        selection_results = []
        totals = {"selected": 0, "total": 0, "phase_1": 0, "phase_2": 0}
        if auto_run_selection:
            from datetime import timedelta as _td
            cur = df
            while cur <= dt:
                try:
                    s = await run_daily_selection(db, client_id, target_date=cur)
                    selection_results.append({
                        "date": str(cur),
                        "ok": s.get("ok"),
                        "total": s.get("total", 0),
                        "selected": s.get("selected", 0),
                        "phase_1": s.get("phase_1", 0),
                        "phase_2": s.get("phase_2", 0),
                    })
                    if s.get("ok"):
                        totals["total"] += s.get("total", 0)
                        totals["selected"] += s.get("selected", 0)
                        totals["phase_1"] += s.get("phase_1", 0)
                        totals["phase_2"] += s.get("phase_2", 0)
                except Exception as e:
                    logger.error(f"[backfill] selection day {cur} error: {e}")
                    selection_results.append({"date": str(cur), "ok": False, "error": str(e)[:200]})
                cur = cur + _td(days=1)

        return {
            "client_id": client_id,
            "date_from": str(df),
            "date_to": str(dt),
            "pages_scanned": pages_scanned,
            "plans_scanned": plans_scanned,
            "plans_in_range": len(in_range_plans),
            "staged": staged,
            "skipped_no_driver": skipped_no_driver,
            "skipped_error": skipped_error,
            "truncated": len(in_range_plans) >= MAX_HYDRATE,
            "max_hydrate_cap": MAX_HYDRATE,
            "auto_run_selection": auto_run_selection,
            "selection_totals": totals,
            "selection_results": selection_results,
        }
    finally:
        try:
            await rc.aclose()
        except Exception:
            pass


@router.post("/selection/reconcile-dates/{client_id}")
async def reconcile_journey_dates(
    client_id: str,
    days_back: int = Query(30, ge=1, le=365, description="Cuántos días atrás revisar (default 30)"),
    dry_run: bool = Query(True, description="Si true, solo reporta sin escribir cambios"),
    user: dict = Depends(get_current_user),
):
    """Reconcilia journey.date contra Routal execution_date para journeys creados vía webhook.

    Lee `journeys` con source='routal' creados en los últimos N días. Para cada uno consulta
    `GET /v2/plan/{routal_plan_id}` y extrae la fecha autoritativa (execution_date). Si difiere
    de journey.date, lista o corrige (según dry_run).

    Resuelve la discrepancia de 1 día reportada cuando webhooks Routal envían `payload.date`
    en formato/timezone inconsistente (vs. `execution_date` que es estable).
    """
    _require_role(user, ["developer"])

    cfg = await db.client_config.find_one({"client_id": client_id}, {"_id": 0})
    if not cfg:
        raise HTTPException(status_code=400, detail="Cliente sin config SEL01")

    from services.integration_service import IntegrationService
    from workers.routal_event_processor import _extract_plan_date
    svc = IntegrationService(db)
    rc = await svc.get_routal_client(client_id)
    if not rc:
        raise HTTPException(status_code=400, detail="Integración Routal inactiva")

    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days_back)
    cutoff_iso = cutoff_dt.isoformat()

    cursor = db.journeys.find(
        {
            "client_id": client_id,
            "source": "routal",
            "routal_plan_id": {"$exists": True, "$ne": None},
            "created_at": {"$gte": cutoff_iso},
        },
        {"_id": 0, "id": 1, "routal_plan_id": 1, "date": 1, "driver_name": 1},
    )
    journeys = [j async for j in cursor]

    discrepancies = []
    fixed = 0
    errors = 0
    try:
        for j in journeys:
            plan_id = j["routal_plan_id"]
            try:
                detail = await rc.get_plan(plan_id)
            except Exception as e:
                errors += 1
                logger.warning(f"[reconcile] get_plan {plan_id} failed: {e}")
                continue
            authoritative_date = _extract_plan_date(detail)
            current_date = j.get("date")
            if current_date != authoritative_date:
                discrepancies.append({
                    "journey_id": j["id"],
                    "routal_plan_id": plan_id,
                    "driver_name": j.get("driver_name"),
                    "current_date": current_date,
                    "authoritative_date": authoritative_date,
                    "execution_date": detail.get("execution_date"),
                    "label": detail.get("label"),
                })
                if not dry_run:
                    await db.journeys.update_one(
                        {"id": j["id"], "client_id": client_id},
                        {"$set": {"date": authoritative_date, "updated_at": _date_to_dt(datetime.now().date()).isoformat()}},
                    )
                    fixed += 1
    finally:
        try:
            await rc.aclose()
        except Exception:
            pass

    return {
        "client_id": client_id,
        "days_back": days_back,
        "dry_run": dry_run,
        "journeys_checked": len(journeys),
        "discrepancies_found": len(discrepancies),
        "fixed": fixed,
        "errors": errors,
        "discrepancies": discrepancies[:100],
    }


@router.get("/selection/summary/{client_id}")
async def get_selection_summary(
    client_id: str,
    date: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    _require_role(user, ["developer", "coordinator", "executive"])
    target = _parse_date(date)
    target_dt = _date_to_dt(target)

    cfg = await db.client_config.find_one({"client_id": client_id}, {"_id": 0})
    if not cfg:
        raise HTTPException(status_code=404, detail=f"client_config no existe para {client_id}")

    cursor = db.driver_audit_log.find(
        {"client_id": client_id, "date": target_dt},
        {"_id": 0},
    )
    rows = [r async for r in cursor]

    selected_rows = [r for r in rows if r.get("selection_status") == "selected"]
    unselected_rows = [r for r in rows if r.get("selection_status") == "unselected"]

    p1 = sum(1 for r in selected_rows if r.get("selection_phase") == "phase_1")
    p2 = sum(1 for r in selected_rows if r.get("selection_phase") == "phase_2")
    if p1 > 0 and p2 == 0:
        phase_applied = "phase_1"
    elif p2 > 0 and p1 == 0:
        phase_applied = "phase_2"
    elif p1 + p2 > 0:
        phase_applied = "mixed"
    else:
        phase_applied = "none"

    drivers_selected = [
        {
            "driver_id": r.get("driver_id"),
            "driver_name": r.get("driver_name"),
            "phase": r.get("selection_phase"),
            "audit_count_30d": r.get("audit_count_30d_at_selection", 0),
            "journey_id": r.get("journey_id"),
            "branch_id": r.get("branch_id"),
        }
        for r in selected_rows
    ]

    # RT-09: per-branch breakdown (multi-project clients) for the day's audit log
    branch_breakdown_raw: dict = {}
    for r in rows:
        bid = r.get("branch_id")
        if not bid:
            continue
        bb = branch_breakdown_raw.setdefault(bid, {"total": 0, "selected": 0})
        bb["total"] += 1
        if r.get("selection_status") == "selected":
            bb["selected"] += 1
    branch_breakdown: dict = {}
    if branch_breakdown_raw:
        branch_codes = {}
        async for b in db.branches.find(
            {"id": {"$in": list(branch_breakdown_raw.keys())}},
            {"_id": 0, "id": 1, "code": 1, "name": 1},
        ):
            branch_codes[b["id"]] = {"code": b.get("code"), "name": b.get("name")}
        for bid, vals in branch_breakdown_raw.items():
            meta = branch_codes.get(bid, {})
            label = meta.get("code") or (bid[:8] if bid else "—")
            branch_breakdown[label] = {
                **vals,
                "branch_id": bid,
                "name": meta.get("name"),
            }

    return {
        "client_id": client_id,
        "date": str(target),
        "total_plans": len(rows),
        "selected": len(selected_rows),
        "unselected": len(unselected_rows),
        "phase_1": p1,
        "phase_2": p2,
        "phase_applied": phase_applied,
        "max_daily_audits": cfg.get("max_daily_audits"),
        "scheduler_time": cfg.get("scheduler_time"),
        "scheduler_times": cfg.get("scheduler_times") or [cfg.get("scheduler_time", "06:00")],
        "selection_enabled": cfg.get("selection_enabled"),
        "last_scheduled_run_date": cfg.get("last_scheduled_run_date"),
        "last_scheduled_run_dates": cfg.get("last_scheduled_run_dates") or {},
        "drivers_selected": drivers_selected,
        "branch_breakdown": branch_breakdown,
    }


@router.get("/selection/branch-history/{client_id}")
async def get_branch_history(
    client_id: str,
    days: int = Query(14, ge=1, le=90),
    user: dict = Depends(get_current_user),
):
    """Sparkline data: per-branch totals/selected for the last N days."""
    _require_role(user, ["developer", "coordinator", "executive"])
    today = datetime.now(CDMX_TZ).date()
    start = today - timedelta(days=days - 1)
    start_dt = _date_to_dt(start)

    pipeline = [
        {"$match": {"client_id": client_id, "date": {"$gte": start_dt}}},
        {
            "$group": {
                "_id": {"date": "$date", "branch_id": "$branch_id"},
                "total": {"$sum": 1},
                "selected": {
                    "$sum": {"$cond": [{"$eq": ["$selection_status", "selected"]}, 1, 0]},
                },
            }
        },
    ]
    rows = await db.driver_audit_log.aggregate(pipeline).to_list(length=2000)

    # Resolve branch ids → codes
    branch_ids = {r["_id"].get("branch_id") for r in rows if r["_id"].get("branch_id")}
    branch_meta: dict = {}
    if branch_ids:
        async for b in db.branches.find(
            {"id": {"$in": list(branch_ids)}},
            {"_id": 0, "id": 1, "code": 1, "name": 1},
        ):
            branch_meta[b["id"]] = {"code": b.get("code"), "name": b.get("name")}

    # Build series indexed by branch code
    series: dict = {}
    for r in rows:
        bid = r["_id"].get("branch_id")
        if not bid:
            continue
        meta = branch_meta.get(bid, {})
        code = meta.get("code") or bid[:8]
        d = r["_id"]["date"]
        d_str = d.strftime("%Y-%m-%d") if isinstance(d, datetime) else str(d)
        s = series.setdefault(code, {
            "branch_id": bid,
            "code": code,
            "name": meta.get("name"),
            "by_date": {},
        })
        s["by_date"][d_str] = {"total": r["total"], "selected": r["selected"]}

    # Materialize one entry per day in the range, even zeros
    all_dates = [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    branches_out = []
    for code, s in sorted(series.items()):
        points = [
            {"date": d, **(s["by_date"].get(d) or {"total": 0, "selected": 0})}
            for d in all_dates
        ]
        branches_out.append({
            "code": code,
            "branch_id": s["branch_id"],
            "name": s["name"],
            "points": points,
            "total_sum": sum(p["total"] for p in points),
            "selected_sum": sum(p["selected"] for p in points),
        })

    return {
        "client_id": client_id,
        "days": days,
        "from": start.strftime("%Y-%m-%d"),
        "to": today.strftime("%Y-%m-%d"),
        "branches": branches_out,
    }


@router.get("/drivers/audit-history/{driver_id}")
async def get_driver_audit_history(
    driver_id: str,
    client_id: str = Query(..., description="client_id requerido"),
    days: int = Query(30, ge=1, le=365),
    user: dict = Depends(get_current_user),
):
    _require_role(user, ["developer", "coordinator"])
    today = datetime.now(CDMX_TZ).date()
    since_dt = _date_to_dt(today - timedelta(days=days))
    cursor = db.driver_audit_log.find(
        {"client_id": client_id, "driver_id": driver_id, "date": {"$gte": since_dt}},
        {"_id": 0},
    ).sort("date", -1)
    rows = [r async for r in cursor]

    driver_name = rows[0]["driver_name"] if rows else None
    selected_count = sum(1 for r in rows if r.get("selection_status") == "selected")

    history = [
        {
            "date": r["date"].strftime("%Y-%m-%d") if isinstance(r.get("date"), datetime) else str(r.get("date")),
            "status": r.get("selection_status"),
            "phase": r.get("selection_phase"),
            "journey_id": r.get("journey_id"),
            "audit_count_30d": r.get("audit_count_30d_at_selection", 0),
        }
        for r in rows
    ]
    return {
        "driver_id": driver_id,
        "driver_name": driver_name,
        "client_id": client_id,
        "days": days,
        "total_audits": selected_count,
        "history": history,
    }


# ─────────────── CLIENT CONFIG ───────────────

class ClientConfigPatch(BaseModel):
    max_daily_audits: Optional[int] = Field(None, gt=0, le=500)
    selection_enabled: Optional[bool] = None
    scheduler_time: Optional[str] = Field(None, description="HH:MM (24h, tz CDMX) — legacy single-time")
    scheduler_times: Optional[List[str]] = Field(None, description="HH:MM array (RT-11 multi-cutoff)")
    active: Optional[bool] = None
    # ─── RTV2 package-oriented cohort (2026-05-30) ───
    audit_target_packages_daily: Optional[int] = Field(None, ge=1, le=100000)
    audit_min_packages_daily: Optional[int] = Field(None, ge=0, le=100000)
    audit_max_packages_daily: Optional[int] = Field(None, ge=1, le=100000)
    audit_target_packages_weekly: Optional[int] = Field(None, ge=1, le=1000000)
    audit_overshoot_tolerance: Optional[float] = Field(None, ge=0.0, le=1.0)
    audit_distribution_strategy: Optional[str] = Field(None, description="'flat' | 'adaptive_calendar_week'")
    audit_safety_circuit_breaker: Optional[int] = Field(None, ge=1, le=100000)
    ingest_cutoff_time: Optional[str] = Field(None, description="HH:MM cutoff for the package-oriented selection")
    ingest_cutoff_timezone: Optional[str] = Field(None, description="IANA TZ (default America/Mexico_City)")
    ingest_eligibility_states: Optional[List[str]] = Field(None, description="Allowed Routal plan states for audit")
    ingest_force_resync_at_cutoff: Optional[bool] = None


@router.get("/client-config")
async def list_client_configs(user: dict = Depends(get_current_user)):
    _require_role(user, ["developer"])
    cursor = db.client_config.find({}, {"_id": 0}).sort("client_name", 1)
    rows = [r async for r in cursor]
    return {"data": rows, "count": len(rows)}


@router.get("/client-config/{client_id}")
async def get_client_config(client_id: str, user: dict = Depends(get_current_user)):
    _require_role(user, ["coordinator", "developer"])
    svc = ClientConfigService(db)
    cfg = await svc.get(client_id)
    if not cfg:
        # Auto-create disabled doc on first read so UI can render the row
        client = await db.clients.find_one({"id": client_id}, {"_id": 0, "name": 1})
        if not client:
            raise HTTPException(status_code=404, detail="cliente no existe")
        cfg = await svc.upsert(client_id=client_id, client_name=client["name"], selection_enabled=False)
    # RTV2: fill in defaults for any missing new field so the UI form always shows
    # populated values even for legacy docs that haven't been migrated yet.
    from services.client_config_service import DEFAULTS
    for k, v in DEFAULTS.items():
        if k not in cfg:
            cfg[k] = v
    return cfg


@router.patch("/client-config/{client_id}")
async def patch_client_config(
    client_id: str,
    payload: ClientConfigPatch,
    user: dict = Depends(get_current_user),
):
    _require_role(user, ["developer"])
    svc = ClientConfigService(db)
    existing = await svc.get(client_id)
    client_name = existing["client_name"] if existing else None
    if not client_name:
        client = await db.clients.find_one({"id": client_id}, {"_id": 0, "name": 1})
        if not client:
            raise HTTPException(status_code=404, detail="cliente no existe")
        client_name = client["name"]
    try:
        cfg = await svc.upsert(
            client_id=client_id,
            client_name=client_name,
            max_daily_audits=payload.max_daily_audits,
            selection_enabled=payload.selection_enabled,
            scheduler_time=payload.scheduler_time,
            scheduler_times=payload.scheduler_times,
            active=payload.active,
            audit_target_packages_daily=payload.audit_target_packages_daily,
            audit_min_packages_daily=payload.audit_min_packages_daily,
            audit_max_packages_daily=payload.audit_max_packages_daily,
            audit_target_packages_weekly=payload.audit_target_packages_weekly,
            audit_overshoot_tolerance=payload.audit_overshoot_tolerance,
            audit_distribution_strategy=payload.audit_distribution_strategy,
            audit_safety_circuit_breaker=payload.audit_safety_circuit_breaker,
            ingest_cutoff_time=payload.ingest_cutoff_time,
            ingest_cutoff_timezone=payload.ingest_cutoff_timezone,
            ingest_eligibility_states=payload.ingest_eligibility_states,
            ingest_force_resync_at_cutoff=payload.ingest_force_resync_at_cutoff,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return cfg


# ─────────────── RTV2 CAPTACIÓN STATS (2026-05-30) ───────────────

@router.get("/captacion/stats/{client_id}")
async def captacion_stats(
    client_id: str,
    days: int = 28,
    user: dict = Depends(get_current_user),
):
    """Aggregated captación metrics for the package-oriented cohort dashboard.

    Returns:
        - today: {date, packages_audited, target_today, adjusted_target, min, max}
        - week: {monday, sunday, target_weekly, accumulated, projected, days_remaining}
        - sparkline: list of {date, packages_audited} for last `days` days
        - last_run: snapshot of most recent selection_runs entry for this client
    """
    _require_role(user, ["coordinator", "developer"])
    from workers.routal_selection_worker import (
        _today_cdmx, _date_to_dt, _calendar_week_bounds,
        compute_adjusted_target_packages,
    )

    cfg = await db.client_config.find_one({"client_id": client_id, "active": True}, {"_id": 0})
    if not cfg:
        raise HTTPException(status_code=404, detail="cliente sin configuración activa")

    today = _today_cdmx()
    monday, sunday = _calendar_week_bounds(today)
    today_dt = _date_to_dt(today)
    monday_dt = _date_to_dt(monday)
    next_monday_dt = _date_to_dt(sunday + timedelta(days=1))

    # Today
    today_pipeline = [
        {"$match": {
            "client_id": client_id, "selection_status": "selected",
            "date": today_dt,
        }},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$packages_audited", 0]}}}},
    ]
    today_total = 0
    async for doc in db.driver_audit_log.aggregate(today_pipeline):
        today_total = int(doc.get("total") or 0)

    # Week accumulated (Mon..Sun)
    week_pipeline = [
        {"$match": {
            "client_id": client_id, "selection_status": "selected",
            "date": {"$gte": monday_dt, "$lt": next_monday_dt},
        }},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$packages_audited", 0]}}}},
    ]
    week_total = 0
    async for doc in db.driver_audit_log.aggregate(week_pipeline):
        week_total = int(doc.get("total") or 0)

    # Adjusted target snapshot
    cohort = await compute_adjusted_target_packages(db, client_id, today, cfg)

    # Sparkline (last `days` days)
    from datetime import date as _date_t
    days_count = max(7, min(int(days or 28), 90))
    spark_start = today - timedelta(days=days_count - 1)
    spark_start_dt = _date_to_dt(spark_start)
    spark_end_dt = _date_to_dt(today + timedelta(days=1))
    spark_pipeline = [
        {"$match": {
            "client_id": client_id, "selection_status": "selected",
            "date": {"$gte": spark_start_dt, "$lt": spark_end_dt},
        }},
        {"$group": {"_id": "$date", "total": {"$sum": {"$ifNull": ["$packages_audited", 0]}}}},
        {"$sort": {"_id": 1}},
    ]
    spark_map: dict = {}
    async for doc in db.driver_audit_log.aggregate(spark_pipeline):
        d = doc["_id"]
        if isinstance(d, datetime):
            d = d.date()
        if isinstance(d, _date_t):
            spark_map[d.isoformat()] = int(doc.get("total") or 0)

    sparkline = []
    for i in range(days_count):
        d = (spark_start + timedelta(days=i)).isoformat()
        sparkline.append({"date": d, "packages_audited": spark_map.get(d, 0)})

    # Last run snapshot
    last_run = await db.selection_runs.find_one(
        {"client_id": client_id}, {"_id": 0}, sort=[("ran_at", -1)]
    )

    days_remaining = (sunday - today).days + 1
    target_daily = int(cfg.get("audit_target_packages_daily", 1000))
    weekly_target = int(cfg.get("audit_target_packages_weekly", 7000))
    # Projected = week_total + (adjusted_target * days_remaining)
    projected = week_total + cohort["adjusted_target"] * days_remaining

    return {
        "client_id": client_id,
        "today": {
            "date": today.isoformat(),
            "packages_audited": today_total,
            "target_daily": target_daily,
            "adjusted_target": cohort["adjusted_target"],
            "min_daily": cohort["min_daily"],
            "max_daily": cohort["max_daily"],
            "pct_of_target": round(today_total / target_daily * 100, 1) if target_daily else 0,
        },
        "week": {
            "monday": monday.isoformat(),
            "sunday": sunday.isoformat(),
            "target_weekly": weekly_target,
            "accumulated": week_total,
            "projected": projected,
            "days_remaining_incl_today": days_remaining,
            "pct_of_weekly_target": round(week_total / weekly_target * 100, 1) if weekly_target else 0,
        },
        "cohort_today": cohort,
        "sparkline": sparkline,
        "last_run": last_run,
        "config_snapshot": {
            "ingest_cutoff_time": cfg.get("ingest_cutoff_time", "16:00"),
            "ingest_cutoff_timezone": cfg.get("ingest_cutoff_timezone", "America/Mexico_City"),
            "ingest_eligibility_states": cfg.get("ingest_eligibility_states", ["in_progress"]),
            "audit_distribution_strategy": cfg.get("audit_distribution_strategy", "adaptive_calendar_week"),
            "audit_safety_circuit_breaker": cfg.get("audit_safety_circuit_breaker", 400),
        },
    }
