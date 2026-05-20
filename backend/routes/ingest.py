"""Ingest routes (PROMPT 04).

  POST /api/guias/ingest/webhook?client_id=...   PUBLIC + HMAC
  POST /api/admin/ingest/layout                  admin+ multipart
  POST /api/admin/ingest/pull/{client_id}         admin+ manual trigger
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from pydantic import BaseModel

from core.config import APP_ENV
from core.errors import (
    ErrorCode, MyEException, ResourceNotFoundException,
)
from core.hmac import verify as hmac_verify
from core.http import get_client_ip
from core.logger import log
from core.rate_limit import hit
from core.response import fail, ok
from middleware.rbac import require_min_role
from models.ingest import WebhookEvent
from repositories.clients import ClientRepository
from repositories.tenants import TenantRepository
from services.ingest_service import IngestService

router_public = APIRouter(prefix="/api/guias/ingest", tags=["ingest-public"])
router_admin = APIRouter(prefix="/api/admin/ingest", tags=["ingest-admin"])

_RBAC = require_min_role("admin")


# ---------- Webhook (public + HMAC) --------------------------------------
@router_public.post("/webhook")
async def webhook(request: Request, client_id: str = Query(..., min_length=36, max_length=36)):
    # Per-IP rate limit (cheap pre-auth defence — R09)
    ip = get_client_ip(request)
    allowed, retry = hit(f"webhook:{ip}", max_hits=120, window_seconds=60)
    if not allowed:
        resp = fail(ErrorCode.RATE_LIMITED, "Demasiadas solicitudes.")
        resp.headers["Retry-After"] = str(retry)
        return resp

    body = await request.body()
    if not body:
        return fail(ErrorCode.VALIDATION_FAILED, "Cuerpo vacío.")

    # Locate client across tenants — webhook is public so we don't have a session
    from core.db import get_db
    raw_client = await get_db()["clients"].find_one({"id": client_id}, {"_id": 0})
    if not raw_client:
        return fail(ErrorCode.AUTH_REQUIRED, "Cliente no encontrado o webhook deshabilitado.")
    if raw_client.get("ingest_mode") != "webhook":
        return fail(ErrorCode.AUTH_REQUIRED, "Cliente no acepta webhook.")

    # Tenant maintenance/suspended check
    tenant = await TenantRepository().col.find_one({"id": raw_client["tenant_id"]}, {"_id": 0})
    if not tenant or tenant.get("status") == "suspended":
        return fail(ErrorCode.TENANT_MAINTENANCE, "Tenant no disponible.")

    # HMAC verification (R06)
    secret = raw_client.get("webhook_token") or ""
    sig = request.headers.get("X-MyE-Signature", "")
    if not hmac_verify(secret, body, sig):
        log.warning("webhook_signature_invalid", extra={"context": {
            "client_id": client_id, "tenant_id": raw_client["tenant_id"], "ip": ip,
        }})
        return fail(ErrorCode.AUTH_REQUIRED, "Firma HMAC inválida.")

    # Parse + validate payload
    try:
        import json
        payload_dict = json.loads(body.decode("utf-8"))
        event = WebhookEvent(**payload_dict)
    except Exception as e:  # noqa: BLE001
        return fail(ErrorCode.VALIDATION_FAILED, f"Payload inválido: {e}")

    svc = IngestService(tenant_id=raw_client["tenant_id"])
    try:
        outcome = await svc.process_event(
            client_id=client_id,
            tracking_id=event.tracking_id,
            carrier_code=event.carrier_code,
            carrier_status=event.carrier_status,
            carrier_status_description=event.carrier_status_description,
            raw_code=event.raw_code,
            api_version=event.api_version,
            event_at=event.event_at,
            raw_payload=event.raw_payload,
            source="webhook",
        )
    except MyEException:
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("webhook_processing_failed")
        if APP_ENV == "production":
            return fail(ErrorCode.INTERNAL_ERROR, "Error procesando el evento.")
        return fail(ErrorCode.INTERNAL_ERROR, str(e))

    return ok({
        "action": outcome.action,
        "guia_id": outcome.guia_id,
        "tracking_id": outcome.tracking_id,
        "is_terminal": outcome.is_terminal,
    }, status_code=202)


# ---------- Layout v2 (CSV/XLSX) upload ---------------------------------
@router_admin.post("/layout")
async def layout_upload(
    request: Request,
    client_id: str = Query(..., min_length=36, max_length=36),
    file: UploadFile = File(...),
    _: object = Depends(_RBAC),
):
    """Layout v2 (Iter39) — Acepta CSV o XLSX con 36 columnas en español.

    Reemplaza el endpoint v1 minimalista. Si necesitás la plantilla,
    descargala desde `GET /api/admin/ingest/layout/template`.
    """
    tenant_id = request.state.user.tenant_id
    # Verify client belongs to the caller's tenant — R01/R08
    if not await ClientRepository(tenant_id=tenant_id).find_one({"id": client_id}):
        raise ResourceNotFoundException("Cliente no encontrado en este tenant.")

    fn = (file.filename or "").lower()
    if not (fn.endswith(".csv") or fn.endswith(".xlsx") or fn.endswith(".xlsm")):
        return fail(ErrorCode.VALIDATION_FAILED,
                    "Sólo se aceptan archivos .csv, .xlsx o .xlsm.",
                    field="file")
    raw = await file.read()
    # Cap 10 MB (XLSX puede ser pesado por estilos/imagenes)
    if len(raw) > 10 * 1024 * 1024:
        return fail(ErrorCode.VALIDATION_FAILED,
                    "Archivo demasiado grande (>10MB).", field="file")

    svc = IngestService(tenant_id=tenant_id)
    try:
        result = await svc.process_layout_file(
            client_id=client_id, file_bytes=raw, filename=file.filename,
        )
    except ValueError as e:
        return fail(ErrorCode.VALIDATION_FAILED, str(e), field="file")
    return ok(result)


@router_admin.get("/layout/template")
async def layout_template(_: object = Depends(_RBAC)):
    """Descarga la plantilla CSV vacía con los 36 headers del layout v2.

    El navegador la guardará como `myexcellence_layout_v2.csv` gracias al
    Content-Disposition.
    """
    from fastapi.responses import Response  # noqa: PLC0415
    from services.ingest.layout_v2 import build_template_csv  # noqa: PLC0415
    return Response(
        content=build_template_csv(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=myexcellence_layout_v2.csv",
        },
    )


class PullRequest(BaseModel):
    """Iter56 — body opcional para pull con rango de fechas."""
    date_from: str | None = None  # ISO date "YYYY-MM-DD" o ISO datetime
    date_to: str | None = None


# ---------- Manual pull (admin) ------------------------------------------
@router_admin.post("/pull/{client_id}")
async def pull(client_id: str, request: Request,
               body: PullRequest | None = None,
               _: object = Depends(_RBAC)):
    tenant_id = request.state.user.tenant_id
    svc = IngestService(tenant_id=tenant_id)
    date_from = body.date_from if body else None
    date_to = body.date_to if body else None
    return ok(await svc.trigger_pull(
        client_id=client_id, date_from=date_from, date_to=date_to))
