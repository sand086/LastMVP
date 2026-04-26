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
from typing import Optional
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
        raise HTTPException(status_code=404, detail=f"client_config no existe para {client_id}")
    summary = await run_daily_selection(db, client_id, target_date=target)
    if not summary.get("ok"):
        raise HTTPException(status_code=400, detail=summary.get("error", "selection failed"))
    return summary


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
        }
        for r in selected_rows
    ]

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
        "selection_enabled": cfg.get("selection_enabled"),
        "last_scheduled_run_date": cfg.get("last_scheduled_run_date"),
        "drivers_selected": drivers_selected,
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
    scheduler_time: Optional[str] = Field(None, description="HH:MM (24h, tz CDMX)")
    active: Optional[bool] = None


@router.get("/client-config")
async def list_client_configs(user: dict = Depends(get_current_user)):
    _require_role(user, ["developer"])
    cursor = db.client_config.find({}, {"_id": 0}).sort("client_name", 1)
    rows = [r async for r in cursor]
    return {"data": rows, "count": len(rows)}


@router.get("/client-config/{client_id}")
async def get_client_config(client_id: str, user: dict = Depends(get_current_user)):
    _require_role(user, ["developer"])
    svc = ClientConfigService(db)
    cfg = await svc.get(client_id)
    if not cfg:
        # Auto-create disabled doc on first read so UI can render the row
        client = await db.clients.find_one({"id": client_id}, {"_id": 0, "name": 1})
        if not client:
            raise HTTPException(status_code=404, detail="cliente no existe")
        cfg = await svc.upsert(client_id=client_id, client_name=client["name"], selection_enabled=False)
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
            active=payload.active,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return cfg
