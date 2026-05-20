"""Iter61 — Enriquecer guías con reports del adapter Routal.

Endpoints:
  POST /api/admin/routal/enrich-reports?client_id=&raw_code=canceled
       Itera guías del cliente y, para cada una, refetcha el stop de Routal
       para extraer ``routal_report`` (motivo del driver, comentarios, fotos)
       y actualiza:
         - guia.carrier_meta.routal_report
         - guia.carrier_incidence = reason_label || comments
         - ticket abierto (si existe): incident_subtype, carrier_incident_detail,
           incident_type = reason_label cuando se conozca.

Idempotente: si la guía ya tiene ``carrier_meta.routal_report`` y se pasa
``skip_existing=true``, se omite la llamada a Routal.
"""
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from core.db import get_db
from core.errors import ResourceNotFoundException
from core.response import ok
from middleware.rbac import require_min_role
from services.cae.adapters.routal import RoutalAdapter, _extract_first_report

router = APIRouter(prefix="/api/admin/routal", tags=["admin-routal-enrich"])

_RBAC = require_min_role("admin")


class EnrichRequest(BaseModel):
    client_id: str
    raw_code: str = "canceled"
    skip_existing: bool = True
    limit: int = 500


async def _resolve_routal_api_key(db, client: dict) -> tuple[str | None, str | None]:
    """Devuelve (api_key, base_url) usando platform → cliente como en _pull_range."""
    from core.crypto import decrypt
    base_url = "https://api.routal.com"
    api_key = None

    pc = await db.platform_carrier_configs.find_one(
        {"code": "routal"}, {"_id": 0})
    if pc and pc.get("enabled") is not False:
        ref = pc.get("api_key_ref")
        if ref:
            try:
                api_key = decrypt(ref)
                base_url = pc.get("base_url") or base_url
            except Exception:
                api_key = None

    carriers_cfg = (client.get("carriers") or {}).get("routal") or {}
    client_ref = carriers_cfg.get("api_key_ref")
    if client_ref:
        try:
            client_key = decrypt(client_ref)
        except Exception:
            client_key = None
        if client_key and len(client_key) >= 20:
            api_key = client_key
        base_url = carriers_cfg.get("base_url") or base_url
    return api_key, base_url


@router.post("/enrich-reports")
async def enrich_reports(payload: EnrichRequest, request: Request,
                          _: object = Depends(_RBAC)):
    db = get_db()
    user = request.state.user

    client = await db.clients.find_one(
        {"id": payload.client_id, "tenant_id": user.tenant_id},
        {"_id": 0})
    if not client:
        raise ResourceNotFoundException("Cliente no encontrado")

    api_key, base_url = await _resolve_routal_api_key(db, client)
    project_ids = ((client.get("carriers") or {}).get("routal") or {}).get(
        "project_ids") or []
    if not api_key or not project_ids:
        return ok({"result": "missing_credentials",
                   "note": "Cliente sin api_key/project_ids de Routal."})

    adapter = RoutalAdapter(api_key=api_key, base_url=base_url,
                            project_ids=project_ids)

    # Construimos un caché local de stops por plan_id para no volver a
    # pegarle a la API por cada guía del mismo plan.
    cache_plan_stops: dict[str, dict] = {}  # plan_id → {stop_id: stop}

    async def _get_stop(plan_id: str, stop_id: str) -> dict | None:
        if plan_id not in cache_plan_stops:
            try:
                stops = await adapter.list_stops_in_plan(plan_id)
            except Exception:
                cache_plan_stops[plan_id] = {}
                return None
            cache_plan_stops[plan_id] = {
                (s.get("id") or s.get("_id")): s for s in stops}
        return cache_plan_stops[plan_id].get(stop_id)

    cursor = db.guias.find({
        "tenant_id": user.tenant_id,
        "client_id": payload.client_id,
        "carrier_code": "routal",
        "raw_code": payload.raw_code,
    }, {"_id": 0}).limit(payload.limit)

    now = datetime.now(timezone.utc).isoformat()
    processed = 0
    enriched_guias = 0
    enriched_tickets = 0
    skipped = 0
    no_report = 0
    errors: list[str] = []

    async for guia in cursor:
        processed += 1
        cm = guia.get("carrier_meta") or {}
        if payload.skip_existing and cm.get("routal_report"):
            skipped += 1
            continue
        plan_id = (guia.get("raw_payload") or {}).get("plan_id")
        stop_id = (guia.get("raw_payload") or {}).get("stop_id")
        if not (plan_id and stop_id):
            errors.append(
                f"{guia.get('tracking_id')}: falta plan_id/stop_id")
            continue
        try:
            stop = await _get_stop(plan_id, stop_id)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{guia.get('tracking_id')}: {str(e)[:120]}")
            continue
        if not stop:
            errors.append(
                f"{guia.get('tracking_id')}: stop no encontrado en Routal")
            continue
        report = _extract_first_report(stop)
        if not report:
            no_report += 1
            continue
        # Actualizar guía
        carrier_meta = dict(cm)
        carrier_meta["routal_report"] = report
        new_carrier_incidence = (guia.get("carrier_incidence")
                                  or report.get("reason_label")
                                  or report.get("comments"))
        await db.guias.update_one(
            {"id": guia["id"]},
            {"$set": {
                "carrier_meta": carrier_meta,
                "carrier_incidence": new_carrier_incidence,
                "updated_at": now,
            }})
        enriched_guias += 1

        # Actualizar ticket abierto (si existe) con detalle del report
        tk = await db.tickets.find_one({
            "guia_id": guia["id"],
            "tenant_id": user.tenant_id,
            "status": {"$in": ["pending", "in_progress",
                                "waiting_client", "waiting_carrier",
                                "claim"]},
        }, {"_id": 0})
        if tk:
            ticket_updates = {
                "carrier_incident_detail": {
                    "report_id": report.get("report_id"),
                    "report_type": report.get("report_type"),
                    "comments": report.get("comments"),
                    "reason_label": report.get("reason_label"),
                    "images": report.get("images"),
                    "images_count": report.get("images_count"),
                    "report_at": report.get("report_at"),
                },
                "updated_at": now,
            }
            if report.get("reason_label"):
                ticket_updates["incident_subtype"] = report["reason_label"]
                # Si el incident_type del ticket es el genérico "exception",
                # lo reemplazamos por el subtipo más descriptivo.
                if tk.get("incident_type") in (None, "", "exception"):
                    ticket_updates["incident_type"] = report["reason_label"]
            await db.tickets.update_one(
                {"id": tk["id"]}, {"$set": ticket_updates})
            enriched_tickets += 1

    return ok({
        "client_id": payload.client_id,
        "raw_code": payload.raw_code,
        "processed": processed,
        "enriched_guias": enriched_guias,
        "enriched_tickets": enriched_tickets,
        "skipped_existing": skipped,
        "no_report_found": no_report,
        "errors": errors[:50],
    })



# ─────────────────────────────────────────────────────────────────────────
# Iter62 — Sintetizar recipient para guías ya cargadas sin Layout V2
# ─────────────────────────────────────────────────────────────────────────
class SynthRecipientRequest(BaseModel):
    client_id: str
    overwrite: bool = False  # si True, reemplaza recipient existente
    limit: int = 10000


@router.post("/synthesize-recipient")
async def synthesize_recipient(payload: SynthRecipientRequest,
                               request: Request,
                               _: object = Depends(_RBAC)):
    """Construye ``guia.recipient`` desde ``raw_payload`` (label/location/
    phone/email) para guías de Routal que se ingestaron antes de Iter62.

    El re-pull naturalmente lo aplicará vía ``process_event`` pero este
    endpoint hace backfill inmediato sin tocar la API de Routal.
    """
    from services.ingest_service import _synthesize_recipient_from_raw_payload

    db = get_db()
    user = request.state.user

    client = await db.clients.find_one(
        {"id": payload.client_id, "tenant_id": user.tenant_id},
        {"_id": 0})
    if not client:
        raise ResourceNotFoundException("Cliente no encontrado")

    match = {
        "tenant_id": user.tenant_id,
        "client_id": payload.client_id,
    }
    if not payload.overwrite:
        match["recipient"] = {"$in": [None, {}]}

    cursor = db.guias.find(match, {"_id": 0, "id": 1, "raw_payload": 1,
                                    "recipient": 1}).limit(payload.limit)
    now = datetime.now(timezone.utc).isoformat()
    processed = 0
    enriched = 0
    skipped = 0
    async for g in cursor:
        processed += 1
        rp = g.get("raw_payload") or {}
        synthesized = _synthesize_recipient_from_raw_payload(rp)
        if not synthesized:
            skipped += 1
            continue
        if not payload.overwrite and g.get("recipient"):
            skipped += 1
            continue
        await db.guias.update_one(
            {"id": g["id"]},
            {"$set": {"recipient": synthesized, "updated_at": now}})
        enriched += 1
    return ok({
        "client_id": payload.client_id,
        "processed": processed,
        "enriched": enriched,
        "skipped": skipped,
    })
