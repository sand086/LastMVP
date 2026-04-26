"""
Integration management endpoints (R00A.4) — all gated by Developer role.
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from dependencies import get_current_user, db
from services.integration_service import IntegrationService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations", tags=["integrations"])

VALID_TYPES = {"kosmo", "routal", "manual"}
VALID_STATUSES = {"active", "inactive", "testing"}


def _require_developer(user: dict):
    if user.get("role") != "developer":
        raise HTTPException(status_code=403, detail="Solo desarrolladores pueden gestionar integraciones")


class IntegrationCredentialsIn(BaseModel):
    routal_api_key: Optional[str] = None
    routal_project_id: Optional[str] = None
    routal_webhook_secret: Optional[str] = None


class IntegrationConfigIn(BaseModel):
    auto_create_journeys: Optional[bool] = None
    auto_close_journeys: Optional[bool] = None
    sync_drivers: Optional[bool] = None


class IntegrationUpsertIn(BaseModel):
    integration_type: str = Field(..., description="kosmo | routal | manual")
    credentials: Optional[IntegrationCredentialsIn] = None
    config: Optional[IntegrationConfigIn] = None
    status: Optional[str] = None


class StatusPatchIn(BaseModel):
    status: str = Field(..., description="active | inactive")


@router.get("")
async def list_integrations(user: dict = Depends(get_current_user)):
    _require_developer(user)
    svc = IntegrationService(db)
    return {"data": await svc.list_integrations_public()}


@router.get("/{client_id}")
async def get_integration(client_id: str, user: dict = Depends(get_current_user)):
    _require_developer(user)
    svc = IntegrationService(db)
    doc = await svc.get_public_integration(client_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Integración no encontrada")
    return doc


@router.post("/{client_id}")
async def upsert_integration(
    client_id: str,
    payload: IntegrationUpsertIn,
    user: dict = Depends(get_current_user),
):
    _require_developer(user)
    if payload.integration_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"integration_type inválido: {payload.integration_type}")

    # Get client_name from clients collection
    client = await db.clients.find_one({"id": client_id}, {"_id": 0, "name": 1})
    if not client:
        raise HTTPException(status_code=404, detail=f"Cliente {client_id} no existe")

    svc = IntegrationService(db)
    creds = payload.credentials.model_dump(exclude_none=True) if payload.credentials else None
    cfg = payload.config.model_dump(exclude_none=True) if payload.config else None

    doc = await svc.upsert_integration(
        client_id=client_id,
        client_name=client.get("name") or client_id,
        integration_type=payload.integration_type,
        credentials=creds,
        config=cfg,
        status=payload.status,
    )
    logger.info(f"[integrations] {user.get('email')} upserted {payload.integration_type} for client {client_id}")
    return doc


@router.patch("/{client_id}/status")
async def update_status(
    client_id: str,
    payload: StatusPatchIn,
    user: dict = Depends(get_current_user),
):
    _require_developer(user)
    if payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="status debe ser 'active', 'inactive' o 'testing'")
    svc = IntegrationService(db)
    doc = await svc.update_status(client_id, payload.status)
    if not doc:
        raise HTTPException(status_code=404, detail="Integración no encontrada")
    logger.info(f"[integrations] {user.get('email')} set status={payload.status} for client {client_id}")
    return doc


@router.post("/{client_id}/test")
async def test_integration(client_id: str, user: dict = Depends(get_current_user)):
    _require_developer(user)
    import time as _time
    t0 = _time.monotonic()

    svc = IntegrationService(db)
    full = await svc.get_client_integration(client_id)
    if not full:
        raise HTTPException(status_code=404, detail="Integración no encontrada")

    integration_type = full.get("integration_type")

    # ─── Kosmo health: no creds; checks scraper freshness for this client ───
    if integration_type == "kosmo":
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        # Last successful Kosmo sync on any journey for this client
        last_journey = await db.journeys.find_one(
            {"client_id": client_id, "last_kosmo_sync_at": {"$exists": True, "$ne": None}},
            {"_id": 0, "last_kosmo_sync_at": 1},
            sort=[("last_kosmo_sync_at", -1)],
        )
        last_sync_at = last_journey.get("last_kosmo_sync_at") if last_journey else None
        last_sync_age_hours = None
        if last_sync_at:
            try:
                ts = datetime.fromisoformat(str(last_sync_at).replace("Z", "+00:00"))
                last_sync_age_hours = round((now - ts).total_seconds() / 3600, 2)
            except Exception:
                last_sync_age_hours = None

        today = now.strftime("%Y-%m-%d")
        active_today = await db.journeys.count_documents(
            {"client_id": client_id, "date": today, "status": {"$in": ["in_progress", "planificada"]}},
        )
        pending_sync = await db.journeys.count_documents(
            {"client_id": client_id, "next_sync_at": {"$exists": True, "$lt": now.isoformat()}},
        )

        if last_sync_age_hours is None:
            scraper_status = "never_synced"
        elif last_sync_age_hours <= 2:
            scraper_status = "ok"
        elif last_sync_age_hours <= 12:
            scraper_status = "stale"
        else:
            scraper_status = "down"

        return {
            "ok": scraper_status in ("ok", "stale"),
            "error": None if scraper_status in ("ok", "stale") else f"scraper {scraper_status}",
            "latency_ms": round((_time.monotonic() - t0) * 1000),
            "type": "kosmo",
            "scraper_status": scraper_status,
            "last_sync_at": last_sync_at,
            "last_sync_age_hours": last_sync_age_hours,
            "journeys_active_today": active_today,
            "journeys_pending_sync": pending_sync,
            "note": "Kosmo no requiere API key — operado por scraper interno",
        }

    # ─── Manual health: client uploads via Layouts (CSV/XLSX) ───
    if integration_type == "manual":
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        thirty_d_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")

        last_journey = await db.journeys.find_one(
            {"client_id": client_id},
            {"_id": 0, "date": 1, "created_at": 1},
            sort=[("date", -1)],
        )
        latest_date = last_journey.get("date") if last_journey else None
        latest_created = last_journey.get("created_at") if last_journey else None

        total_journeys = await db.journeys.count_documents({"client_id": client_id})
        recent_journeys = await db.journeys.count_documents(
            {"client_id": client_id, "date": {"$gte": thirty_d_ago}},
        )

        if total_journeys == 0:
            manual_status = "empty"
            error = "Sin layouts cargados. Sube uno en /upload."
        elif recent_journeys == 0:
            manual_status = "dormant"
            error = f"Sin actividad en últimos 30 días (último: {latest_date})"
        else:
            manual_status = "ok"
            error = None

        return {
            "ok": manual_status == "ok",
            "error": error,
            "latency_ms": round((_time.monotonic() - t0) * 1000),
            "type": "manual",
            "manual_status": manual_status,
            "total_journeys": total_journeys,
            "recent_journeys_30d": recent_journeys,
            "latest_journey_date": latest_date,
            "latest_journey_created_at": latest_created,
            "note": "Manual: cliente sube data vía Layouts (CSV/XLSX) — sin sync automático",
        }

    # ─── Routal: real API call with credentials ───
    if integration_type != "routal":
        return {"ok": False, "error": f"Tipo desconocido: {integration_type}", "latency_ms": 0, "type": integration_type}

    creds = full.get("credentials") or {}
    api_key = creds.get("routal_api_key")
    project_id = creds.get("routal_project_id")
    if not api_key or not project_id:
        return {"ok": False, "error": "Faltan API key o Project ID", "latency_ms": 0, "type": "routal"}

    from services.routal_client import RoutalClient
    rc = RoutalClient(api_key=api_key, project_id=project_id)
    try:
        result = await rc.test_connection()
    finally:
        await rc.aclose()
    return {**result, "type": "routal"}


@router.delete("/{client_id}")
async def delete_integration(client_id: str, user: dict = Depends(get_current_user)):
    _require_developer(user)
    svc = IntegrationService(db)
    ok = await svc.soft_delete(client_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Integración no encontrada")
    logger.warning(f"[integrations] {user.get('email')} soft-deleted client {client_id}")
    return {"ok": True}
