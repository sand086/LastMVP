"""Routes /api/admin/webhooks (PROMPT 39 V3).

Endpoints (todos requieren admin+; DLQ replay/archive y rotation requieren
superadmin/root_dev por su impacto):

  GET    /api/admin/webhooks/events                  — catálogo
  POST   /api/admin/webhooks/events                  — crear (root_dev|superadmin)
  PATCH  /api/admin/webhooks/events/{event_code}     — toggle active (root_dev|superadmin)

  GET    /api/admin/webhooks/subscriptions           — listar
  POST   /api/admin/webhooks/subscriptions           — crear (admin+)
  PATCH  /api/admin/webhooks/subscriptions/{id}      — actualizar (admin+)
  POST   /api/admin/webhooks/subscriptions/{id}/rotate-secret — P1.3
  POST   /api/admin/webhooks/subscriptions/{id}/revoke-pii    — revocar consent
  GET    /api/admin/webhooks/subscriptions/{id}/health        — P1.6

  GET    /api/admin/webhooks/deliveries              — log filtrable
  GET    /api/admin/webhooks/dlq                     — DLQ no resueltos
  POST   /api/admin/webhooks/dlq/{id}/replay         — superadmin
  DELETE /api/admin/webhooks/dlq/{id}                — archivar (superadmin)

  GET    /api/admin/webhooks/events/{event_code}/sample  — P1.4 sample payload
  POST   /api/admin/webhooks/worker/tick                 — debug (root_dev)
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, Path, Query, Request

from core.errors import ResourceNotFoundException
from core.response import fail, ok
from middleware.rbac import require_min_role, require_role
from models.webhook import (
    FeatureCatalogCreate, WebhookSubscriptionCreate, WebhookSubscriptionUpdate,
)
from repositories.clients import ClientRepository
from repositories.webhooks import (
    WebhookDeadLetterQueueRepository, WebhookDeliveryLogRepository,
    WebhookEventCatalogRepository, WebhookPendingQueueRepository,
    WebhookSubscriptionRepository,
)
from services.webhooks.dispatcher import worker_tick
from services.webhooks.security import (
    encrypt_secret, generate_secret,
)
from services.webhooks.url_validator import SsrfBlocked, validate_static


router = APIRouter(prefix="/api/admin/webhooks", tags=["webhooks-admin"])

_RBAC_ADMIN = require_min_role("admin")
_RBAC_SUPER = require_role("root_dev", "superadmin")


def _tenant(request: Request) -> str:
    return request.state.user.tenant_id


def _user_id(request: Request) -> str:
    return request.state.user.id


@router.get("/dashboard")
async def webhooks_dashboard(request: Request,
                              hours: int = Query(default=24, ge=1, le=168),
                              _: object = Depends(_RBAC_ADMIN)):
    """Dashboard tenant-wide: KPIs + top 5 endpoints frágiles + DLQ por evento.

    Métricas:
      - totals (deliveries 24h, success rate, avg_latency, dlq_count, paused/circuit_open)
      - top_fragile_endpoints: top 5 con peor success_rate (mín 5 intentos)
      - by_event_code: counts agregados por event_code
    """
    tenant_id = _tenant(request)
    db_root = WebhookDeliveryLogRepository(tenant_id=tenant_id).col.database
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    log_col = db_root["webhook_delivery_log"]
    sub_col = db_root["webhook_subscriptions"]

    # Totals
    pipeline = [
        {"$match": {"tenant_id": tenant_id, "created_at": {"$gte": cutoff}}},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
            "avg_latency": {"$avg": "$latency_ms"},
        }},
    ]
    by_status: dict = {}
    total = 0
    delivered = 0
    avg_latency = 0.0
    async for row in log_col.aggregate(pipeline):
        by_status[row["_id"]] = row["count"]
        total += row["count"]
        if row["_id"] == "delivered":
            delivered = row["count"]
            avg_latency = row.get("avg_latency") or 0.0
    success_rate = (delivered / total) if total else 1.0

    # Top fragile endpoints (mín 5 intentos en la ventana, peor success_rate)
    fragile_pipeline = [
        {"$match": {"tenant_id": tenant_id, "created_at": {"$gte": cutoff}}},
        {"$group": {
            "_id": "$subscription_id",
            "total": {"$sum": 1},
            "delivered": {"$sum": {"$cond": [{"$eq": ["$status", "delivered"]}, 1, 0]}},
            "failed": {"$sum": {"$cond": [
                {"$in": ["$status", ["failed_temporary", "failed_permanent",
                                      "timeout", "circuit_open"]]},
                1, 0,
            ]}},
            "avg_latency": {"$avg": "$latency_ms"},
        }},
        {"$match": {"total": {"$gte": 5}}},
        {"$addFields": {
            "success_rate": {"$divide": ["$delivered", "$total"]},
        }},
        {"$sort": {"success_rate": 1, "total": -1}},
        {"$limit": 5},
    ]
    fragile: list[dict] = []
    async for row in log_col.aggregate(fragile_pipeline):
        sub = await sub_col.find_one(
            {"id": row["_id"], "tenant_id": tenant_id},
            {"_id": 0, "endpoint_url": 1, "client_id": 1,
             "is_circuit_open": 1, "is_paused": 1},
        )
        if not sub:
            continue
        fragile.append({
            "subscription_id": row["_id"],
            "endpoint_url": sub.get("endpoint_url"),
            "client_id": sub.get("client_id"),
            "total_attempts": row["total"],
            "delivered": row["delivered"],
            "failed": row["failed"],
            "success_rate": round(row["success_rate"], 4),
            "avg_latency_ms": round(row["avg_latency"] or 0, 1),
            "is_circuit_open": bool(sub.get("is_circuit_open")),
            "is_paused": bool(sub.get("is_paused")),
        })

    # By event_code
    by_event: dict = {}
    pipeline_event = [
        {"$match": {"tenant_id": tenant_id, "created_at": {"$gte": cutoff}}},
        {"$group": {"_id": "$event_code", "count": {"$sum": 1},
                    "delivered": {"$sum": {"$cond": [{"$eq": ["$status", "delivered"]}, 1, 0]}}}},
        {"$sort": {"count": -1}},
        {"$limit": 20},
    ]
    async for row in log_col.aggregate(pipeline_event):
        by_event[row["_id"]] = {
            "total": row["count"],
            "delivered": row["delivered"],
            "success_rate": round(row["delivered"] / row["count"], 4) if row["count"] else 1.0,
        }

    # Cuentas adicionales
    sub_total = await sub_col.count_documents({"tenant_id": tenant_id})
    sub_active = await sub_col.count_documents({"tenant_id": tenant_id, "is_active": True})
    sub_circuit_open = await sub_col.count_documents(
        {"tenant_id": tenant_id, "is_circuit_open": True},
    )
    sub_paused = await sub_col.count_documents(
        {"tenant_id": tenant_id, "is_paused": True},
    )
    dlq_open = await db_root["webhook_dead_letter_queue"].count_documents(
        {"tenant_id": tenant_id, "resolved": False},
    )

    return ok({
        "window_hours": hours,
        "totals": {
            "total_attempts": total,
            "delivered": delivered,
            "success_rate": round(success_rate, 4),
            "avg_latency_ms": round(avg_latency, 1),
            "by_status": by_status,
        },
        "subscriptions": {
            "total": sub_total, "active": sub_active,
            "circuit_open": sub_circuit_open, "paused": sub_paused,
        },
        "dlq_unresolved": dlq_open,
        "top_fragile_endpoints": fragile,
        "by_event_code": by_event,
    })


# ────────────────────────── Catálogo ─────────────────────────────────────
@router.get("/events")
async def list_events(request: Request, _: object = Depends(_RBAC_ADMIN)):
    repo = WebhookEventCatalogRepository(tenant_id=_tenant(request))
    items = await repo.list_active()
    return ok({"items": items, "count": len(items)})


@router.post("/events", status_code=201)
async def create_event(body: FeatureCatalogCreate,
                       _: object = Depends(_RBAC_SUPER)):
    repo = WebhookEventCatalogRepository()
    if await repo.by_code(body.event_code, schema_version=body.schema_version):
        return fail("VALIDATION_FAILED",
                    f"Ya existe evento '{body.event_code}' v{body.schema_version}.",
                    field="event_code")
    doc = await repo.upsert_global(body.model_dump())
    return ok(doc, status_code=201)


@router.patch("/events/{event_code}")
async def patch_event(event_code: str = Path(...),
                       active: Optional[bool] = Body(default=None, embed=True),
                       _: object = Depends(_RBAC_SUPER)):
    if active is None:
        return fail("VALIDATION_FAILED", "active es requerido.")
    repo = WebhookEventCatalogRepository()
    r = await repo.col.update_many(
        {"event_code": event_code, "tenant_id": None},
        {"$set": {"active": active, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if r.matched_count == 0:
        raise ResourceNotFoundException()
    return ok({"event_code": event_code, "active": active})


# ────────────────────────── Suscripciones ────────────────────────────────
@router.get("/subscriptions")
async def list_subscriptions(request: Request,
                              client_id: Optional[str] = Query(default=None),
                              _: object = Depends(_RBAC_ADMIN)):
    repo = WebhookSubscriptionRepository(tenant_id=_tenant(request))
    items = await repo.list_for_tenant()
    if client_id:
        items = [it for it in items if it.get("client_id") == client_id]
    return ok({"items": items, "count": len(items)})


@router.post("/subscriptions", status_code=201)
async def create_subscription(body: WebhookSubscriptionCreate, request: Request,
                               _: object = Depends(_RBAC_ADMIN)):
    tenant_id = _tenant(request)

    # Validar cliente del tenant
    if not await ClientRepository(tenant_id=tenant_id).find_one({"id": body.client_id}):
        raise ResourceNotFoundException("Cliente no existe en este tenant.")

    # R45 — validación SSRF estática
    try:
        validate_static(body.endpoint_url, allow_extra_ports=body.allow_extra_ports)
    except SsrfBlocked as e:
        return fail("VALIDATION_FAILED", f"[{e.code}] {e.message}",
                    field="endpoint_url")

    # Validar event_codes existen en catálogo
    cat_repo = WebhookEventCatalogRepository(tenant_id=tenant_id)
    for code in body.event_codes:
        if not await cat_repo.by_code(code):
            return fail("VALIDATION_FAILED",
                        f"Evento '{code}' no está en el catálogo activo.",
                        field="event_codes")

    # R49 — include_pii=true requiere consent
    if body.include_pii and not (body.pii_consent_signature or "").strip():
        return fail("VALIDATION_FAILED",
                    "include_pii=true requiere pii_consent_signature.",
                    field="pii_consent_signature")

    # Generar secreto HMAC y cifrar
    secret_plain = generate_secret()
    secret_enc = encrypt_secret(secret_plain)
    import hashlib
    repo = WebhookSubscriptionRepository(tenant_id=tenant_id)
    doc = await repo.create({
        "client_id": body.client_id,
        "endpoint_url": body.endpoint_url,
        "endpoint_url_hash": hashlib.sha256(body.endpoint_url.encode()).hexdigest(),
        "hmac_secret_encrypted": secret_enc,
        "event_codes": body.event_codes,
        "filter_jsonpath": body.filter_jsonpath,
        "include_pii": body.include_pii,
        "pii_consent_at": (datetime.now(timezone.utc).isoformat()
                            if body.include_pii else None),
        "pii_consent_signature": body.pii_consent_signature if body.include_pii else None,
        "allow_extra_ports": body.allow_extra_ports,
        "created_by": _user_id(request),
    })
    # Strip secrets del response y devolver el plano UNA vez
    safe = {k: v for k, v in doc.items()
            if k not in ("hmac_secret_encrypted", "hmac_secret_v2_encrypted")}
    safe["hmac_secret"] = secret_plain
    safe["hmac_secret_warning"] = (
        "Guarda este secreto. No se mostrará nuevamente. "
        "Úsalo para verificar el header X-MyE-Signature."
    )
    return ok({"subscription": safe}, status_code=201)


@router.patch("/subscriptions/{subscription_id}")
async def patch_subscription(subscription_id: str, body: WebhookSubscriptionUpdate,
                              request: Request, _: object = Depends(_RBAC_ADMIN)):
    repo = WebhookSubscriptionRepository(tenant_id=_tenant(request))
    if not await repo.get(subscription_id):
        raise ResourceNotFoundException()

    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if "endpoint_url" in updates:
        try:
            validate_static(updates["endpoint_url"])
        except SsrfBlocked as e:
            return fail("VALIDATION_FAILED", f"[{e.code}] {e.message}",
                        field="endpoint_url")
        import hashlib
        updates["endpoint_url_hash"] = hashlib.sha256(
            updates["endpoint_url"].encode()
        ).hexdigest()
    if "event_codes" in updates:
        cat_repo = WebhookEventCatalogRepository(tenant_id=_tenant(request))
        for code in updates["event_codes"]:
            if not await cat_repo.by_code(code):
                return fail("VALIDATION_FAILED",
                            f"Evento '{code}' no está en catálogo.",
                            field="event_codes")
    await repo.patch(subscription_id, updates)
    return ok(await repo.get(subscription_id))


@router.post("/subscriptions/{subscription_id}/rotate-secret")
async def rotate_secret(subscription_id: str, request: Request,
                         _: object = Depends(_RBAC_SUPER)):
    """P1.3 — rota el secreto. El viejo se mantiene 7 días en X-MyE-Signature
    y el nuevo en X-MyE-Signature-V2. Tras 7 días, viejo se descarta."""
    repo = WebhookSubscriptionRepository(tenant_id=_tenant(request))
    sub = await repo.get(subscription_id)
    if not sub:
        raise ResourceNotFoundException()
    new_plain = generate_secret()
    new_enc = encrypt_secret(new_plain)
    until = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    # El antiguo pasa a "v2" temporal y el nuevo es el primario.
    full = await repo.col.find_one(
        {"id": subscription_id, "tenant_id": _tenant(request)}, {"_id": 0},
    )
    old_enc = full.get("hmac_secret_encrypted")
    await repo.patch(subscription_id, {
        "hmac_secret_encrypted": new_enc,
        "hmac_secret_v2_encrypted": old_enc,
        "hmac_v2_until": until,
    })
    return ok({
        "subscription_id": subscription_id,
        "new_hmac_secret": new_plain,
        "old_secret_active_until": until,
        "hmac_secret_warning": "Guarda este secreto. No se mostrará nuevamente.",
    })


@router.post("/subscriptions/{subscription_id}/revoke-pii")
async def revoke_pii(subscription_id: str, request: Request,
                      _: object = Depends(_RBAC_ADMIN)):
    repo = WebhookSubscriptionRepository(tenant_id=_tenant(request))
    if not await repo.get(subscription_id):
        raise ResourceNotFoundException()
    await repo.patch(subscription_id, {
        "include_pii": False,
        "pii_consent_at": None,
        "pii_consent_signature": None,
    })
    return ok({"subscription_id": subscription_id, "include_pii": False})


@router.get("/subscriptions/{subscription_id}/health")
async def subscription_health(subscription_id: str, request: Request,
                               _: object = Depends(_RBAC_ADMIN)):
    """P1.6 — métricas de salud por suscripción."""
    tenant_id = _tenant(request)
    repo = WebhookSubscriptionRepository(tenant_id=tenant_id)
    sub = await repo.get(subscription_id)
    if not sub:
        raise ResourceNotFoundException()
    log_repo = WebhookDeliveryLogRepository(tenant_id=tenant_id)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    pipeline = [
        {"$match": {"tenant_id": tenant_id, "subscription_id": subscription_id,
                    "created_at": {"$gte": cutoff}}},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
            "avg_latency": {"$avg": "$latency_ms"},
        }},
    ]
    by_status: dict = {}
    avg_latency = 0.0
    total = 0
    delivered = 0
    async for row in log_repo.col.aggregate(pipeline):
        by_status[row["_id"]] = row["count"]
        if row["avg_latency"]:
            avg_latency = max(avg_latency, row["avg_latency"])
        total += row["count"]
        if row["_id"] == "delivered":
            delivered = row["count"]

    # Pendientes en queue
    queue = WebhookPendingQueueRepository(tenant_id=tenant_id)
    pending = await queue.col.count_documents({
        "tenant_id": tenant_id, "subscription_id": subscription_id,
    })
    # DLQ acumulado
    dlq = await WebhookDeadLetterQueueRepository(tenant_id=tenant_id).col.count_documents({
        "tenant_id": tenant_id, "subscription_id": subscription_id, "resolved": False,
    })
    success_rate = (delivered / total) if total else 1.0
    # P1.1 — CB metrics live
    from services.webhooks.circuit_breaker import compute_failure_rate
    cb_metrics = await compute_failure_rate(
        tenant_id=tenant_id, subscription_id=subscription_id,
    )
    return ok({
        "subscription_id": subscription_id,
        "window_hours": 24,
        "by_status": by_status,
        "total_attempts": total,
        "delivered": delivered,
        "success_rate": round(success_rate, 4),
        "avg_latency_ms": round(avg_latency, 1),
        "pending_in_queue": pending,
        "dlq_unresolved": dlq,
        "is_circuit_open": bool(sub.get("is_circuit_open")),
        "circuit_open_until": sub.get("circuit_open_until"),
        "circuit_metrics_1h": cb_metrics,
    })


@router.post("/subscriptions/{subscription_id}/reset-circuit")
async def reset_circuit(subscription_id: str, request: Request,
                         _: object = Depends(_RBAC_ADMIN)):
    """P1.1 — manual close (override). Útil tras un incidente confirmado
    como resuelto cuando el circuito sigue abierto por inercia."""
    repo = WebhookSubscriptionRepository(tenant_id=_tenant(request))
    if not await repo.get(subscription_id):
        raise ResourceNotFoundException()
    await repo.patch(subscription_id, {
        "is_circuit_open": False,
        "circuit_open_until": None,
        "circuit_manually_reset_at": datetime.now(timezone.utc).isoformat(),
        "circuit_manually_reset_by": _user_id(request),
    })
    return ok({"subscription_id": subscription_id, "is_circuit_open": False})


# ────────────────────────── Deliveries log ──────────────────────────────
@router.get("/deliveries")
async def list_deliveries(request: Request,
                           subscription_id: Optional[str] = Query(default=None),
                           event_id: Optional[str] = Query(default=None),
                           status: Optional[str] = Query(default=None),
                           limit: int = Query(default=200, ge=1, le=1000),
                           _: object = Depends(_RBAC_ADMIN)):
    repo = WebhookDeliveryLogRepository(tenant_id=_tenant(request))
    q: dict = {}
    if subscription_id:
        q["subscription_id"] = subscription_id
    if event_id:
        q["event_id"] = event_id
    if status:
        q["status"] = status
    items = await repo.query(q, limit=limit)
    return ok({"items": items, "count": len(items)})


# ────────────────────────── DLQ ──────────────────────────────────────────
@router.get("/dlq")
async def list_dlq(request: Request, _: object = Depends(_RBAC_ADMIN)):
    repo = WebhookDeadLetterQueueRepository(tenant_id=_tenant(request))
    items = await repo.list_unresolved(limit=200)
    return ok({"items": items, "count": len(items)})


@router.post("/dlq/{dlq_id}/replay")
async def replay_dlq(dlq_id: str, request: Request,
                      _: object = Depends(_RBAC_SUPER)):
    """Reencola el evento desde DLQ. Resetea attempts a 0."""
    tenant_id = _tenant(request)
    dlq = WebhookDeadLetterQueueRepository(tenant_id=tenant_id)
    doc = await dlq.col.find_one({"id": dlq_id, "tenant_id": tenant_id,
                                  "resolved": False}, {"_id": 0})
    if not doc:
        raise ResourceNotFoundException()
    queue = WebhookPendingQueueRepository(tenant_id=tenant_id)
    await queue.enqueue({
        "subscription_id": doc["subscription_id"],
        "event_id": doc["event_id"],
        "event_type": doc["event_code"],
        "source_id": doc.get("source_id"),
        "payload": doc["payload"],
        "pii_masked": False,
    })
    await dlq.mark_resolved(dlq_id, action="replayed", user_id=_user_id(request))
    return ok({"dlq_id": dlq_id, "replayed": True})


@router.delete("/dlq/{dlq_id}")
async def archive_dlq(dlq_id: str, request: Request,
                       _: object = Depends(_RBAC_SUPER)):
    repo = WebhookDeadLetterQueueRepository(tenant_id=_tenant(request))
    if not await repo.col.find_one({"id": dlq_id, "tenant_id": _tenant(request),
                                    "resolved": False}, {"_id": 0}):
        raise ResourceNotFoundException()
    await repo.mark_resolved(dlq_id, action="archived", user_id=_user_id(request))
    return ok({"dlq_id": dlq_id, "archived": True})


@router.post("/subscriptions/{subscription_id}/pause")
async def pause_subscription(subscription_id: str, request: Request,
                              _: object = Depends(_RBAC_ADMIN)):
    """P2 burst mode — pausa sin descartar eventos. Worker los conserva
    en queue y reintenta cada 5min hasta unpause."""
    repo = WebhookSubscriptionRepository(tenant_id=_tenant(request))
    if not await repo.get(subscription_id):
        raise ResourceNotFoundException()
    await repo.patch(subscription_id, {
        "is_paused": True,
        "paused_at": datetime.now(timezone.utc).isoformat(),
        "paused_by": _user_id(request),
    })
    return ok({"subscription_id": subscription_id, "is_paused": True})


@router.post("/subscriptions/{subscription_id}/resume")
async def resume_subscription(subscription_id: str, request: Request,
                               _: object = Depends(_RBAC_ADMIN)):
    repo = WebhookSubscriptionRepository(tenant_id=_tenant(request))
    if not await repo.get(subscription_id):
        raise ResourceNotFoundException()
    await repo.patch(subscription_id, {
        "is_paused": False,
        "resumed_at": datetime.now(timezone.utc).isoformat(),
        "resumed_by": _user_id(request),
    })
    return ok({"subscription_id": subscription_id, "is_paused": False})


@router.get("/subscriptions/{subscription_id}/readme")
async def subscription_readme(subscription_id: str, request: Request,
                               _: object = Depends(_RBAC_ADMIN)):
    """P2 — README markdown self-contained con headers, retries, y ejemplos
    de verificación HMAC en Node/Python/PHP/cURL para el cliente."""
    from fastapi.responses import Response
    from services.webhooks.readme_generator import generate_readme
    sub = await WebhookSubscriptionRepository(
        tenant_id=_tenant(request),
    ).get(subscription_id)
    if not sub:
        raise ResourceNotFoundException()
    # Cargar samples de los eventos suscritos
    samples = {}
    cat_repo = WebhookEventCatalogRepository(tenant_id=_tenant(request))
    for code in sub.get("event_codes") or []:
        cat = await cat_repo.by_code(code)
        if not cat:
            continue
        # Reusar sample_payload route logic (data hardcoded)
        samples[code] = {
            "event_id": "00000000-0000-0000-0000-000000000000",
            "event_type": code,
            "schema_version": cat["schema_version"],
            "occurred_at": "2027-09-25T14:23:11Z",
            "data": SAMPLE_DATA_BY_CODE.get(code, {}),
        }
    md = generate_readme(
        subscription=sub,
        event_codes=sub.get("event_codes") or [],
        samples_by_code=samples,
    )
    fname = f"webhook-{subscription_id[:8]}.md"
    return Response(
        content=md, media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# Datos de muestra reutilizados por sample_payload y readme
SAMPLE_DATA_BY_CODE = {
    "ticket.created": {
        "ticket": {
            "id": "INC-3421", "client_id": "11111111-...", "carrier_id": "fedex",
            "guia_id": "22222222-...", "tracking_id": "728198341",
            "status": "pending", "motivo_id": "DIR_INSUFICIENTE",
            "incident_type": "address_issue",
            "destinatario": {"name": "[NAME_a1b2c3]",
                              "address_summary": "Col. Doctores, CDMX"},
            "created_at": "2027-09-25T14:23:11Z",
        },
    },
    "ticket.status_changed": {
        "ticket_id": "INC-3421", "previous_status": "pending",
        "new_status": "in_progress", "actor_id": None, "reason": None,
    },
    "ticket.closed": {"ticket_id": "INC-3421", "final_status": "resolved",
                      "closed_by": None},
    "claim.conciliated": {"claim_id": "CLM-100", "ticket_id": "INC-3421",
                          "monto_aprobado": 1500.0, "moneda": "MXN"},
    "guia.delivered": {"guia_id": "22222222-...", "client_id": "11111111-...",
                        "carrier_id": "fedex", "tracking_id": "728198341",
                        "delivered_at": "2027-09-25T14:23:11Z"},
}


# ────────────────────────── Sample payload (P1.4) ────────────────────────
SAMPLE_TICKET = {
    "ticket": {
        "id": "INC-3421",
        "client_id": "11111111-1111-1111-1111-111111111111",
        "carrier_id": "fedex",
        "guia_id": "22222222-2222-2222-2222-222222222222",
        "tracking_id": "728198341",
        "status": "pending",
        "motivo_id": "DIR_INSUFICIENTE",
        "incident_type": "address_issue",
        "destinatario": {
            "name": "[NAME_a1b2c3]",
            "address_summary": "Col. Doctores, CDMX",
        },
        "created_at": "2027-09-25T14:23:11Z",
    },
}


@router.get("/events/{event_code}/sample")
async def sample_payload(event_code: str, _: object = Depends(_RBAC_ADMIN)):
    repo = WebhookEventCatalogRepository()
    cat = await repo.by_code(event_code)
    if not cat:
        raise ResourceNotFoundException()
    sample = {
        "event_id": "7f8c2d3e-1111-2222-3333-444444444444",
        "event_type": event_code,
        "schema_version": cat["schema_version"],
        "occurred_at": "2027-09-25T14:23:11Z",
        "tenant_id": "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
        "data": SAMPLE_DATA_BY_CODE.get(event_code, {}),
    }
    return ok({"sample_payload": sample, "schema": cat.get("payload_schema")})


# ────────────────────────── Worker debug ─────────────────────────────────
@router.post("/worker/tick")
async def force_worker_tick(request: Request, _: object = Depends(_RBAC_SUPER),
                             batch: int = Query(default=25, ge=1, le=200)):
    """Debug — fuerza una pasada del worker. Útil en pruebas e2e."""
    res = await worker_tick(batch=batch)
    return ok(res)
