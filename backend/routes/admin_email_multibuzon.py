"""Bundle G · FASE 2 — Endpoints admin para email multi-buzón.

Rutas:
  /api/admin/email/domains            GET POST DELETE
  /api/admin/email/domains/{id}/verify POST
  /api/admin/email/mailboxes          GET POST
  /api/admin/email/mailboxes/{id}     PATCH DELETE
  /api/admin/email/mailboxes/{id}/test POST
  /api/admin/email/routing            GET POST DELETE
  /api/admin/email/explain            POST  (dry-run de resolución)
  /api/admin/email/health             GET   (métricas)
  /api/admin/email/logs               GET
"""
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Query
from pydantic import BaseModel, Field

from core.crypto import encrypt
from core.db import get_db
from core.errors import MyEException, ErrorCode, ResourceNotFoundException
from core.response import ok
from core.uuid import new_id
from middleware.rbac import require_min_role
from models.email_multibuzon import (
    DomainCreate, MailboxCreate, MailboxUpdate, RoutingRuleCreate,
    EmailContext, EmailPayload, public_domain, public_mailbox,
)
from repositories.email_multibuzon import (
    EmailDomainRepository, EmailMailboxRepository,
    EmailRoutingRepository, EmailSendLogRepository,
    make_domain_doc, make_mailbox_doc, make_routing_doc,
)
from services.email_dispatcher import EmailDispatcher


router = APIRouter(prefix="/api/admin/email", tags=["admin-email-mb"])
_RBAC = require_min_role("admin")


def _val(msg: str, field: str | None = None) -> MyEException:
    return MyEException(ErrorCode.VALIDATION_FAILED, msg, field=field)


# ──────────────────────────────────────────────────────────────
# DOMAINS
# ──────────────────────────────────────────────────────────────
@router.get("/domains")
async def list_domains(request: Request, _: object = Depends(_RBAC)):
    repo = EmailDomainRepository(tenant_id=request.state.user.tenant_id)
    items = await repo.find({}, limit=200, sort=[("created_at", -1)])
    return ok({"items": [public_domain(d) for d in items], "count": len(items)})


def _dns_records_for(domain: str) -> list[dict]:
    """Devuelve los DNS records placeholder. En producción se obtendrían
    de la API de Resend (`domains.create`)."""
    return [
        {"type": "TXT", "name": domain,
         "value": "v=spf1 include:_spf.resend.com ~all", "purpose": "SPF"},
        {"type": "TXT", "name": f"resend._domainkey.{domain}",
         "value": "p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQ...",
         "purpose": "DKIM (placeholder — Resend te dará el real)"},
        {"type": "TXT", "name": f"_dmarc.{domain}",
         "value": "v=DMARC1; p=none; rua=mailto:dmarc@" + domain,
         "purpose": "DMARC"},
        {"type": "MX", "name": f"send.{domain}",
         "value": "feedback-smtp.us-east-1.amazonses.com", "priority": 10,
         "purpose": "MX (envío)"},
    ]


@router.post("/domains", status_code=201)
async def add_domain(payload: DomainCreate, request: Request,
                      _: object = Depends(_RBAC)):
    user = request.state.user
    db = get_db()
    domain = payload.domain.lower()
    existing = await db.email_domains.find_one(
        {"tenant_id": user.tenant_id, "domain": domain}, {"_id": 0})
    if existing:
        raise _val("Ese dominio ya está registrado para este tenant.", "domain")
    doc = make_domain_doc(
        tenant_id=user.tenant_id, domain=domain,
        created_by=user.id, provider=payload.provider,
        verification_status="pending", dkim=False, spf=False, dmarc=False,
        dns_records=_dns_records_for(domain),
    )
    await db.email_domains.insert_one(doc)
    return ok(public_domain(doc), status_code=201)


@router.post("/domains/{domain_id}/verify")
async def verify_domain(domain_id: str, request: Request,
                         _: object = Depends(_RBAC)):
    """Marcar dominio como verificado.

    Nota: la verificación DNS real se hace en FASE 3 contra Resend. Por ahora
    asumimos verified si el admin lo confirma (lo cual es lo que pasa en
    el wizard tras seguir las instrucciones). Cuando se cablee la API de
    Resend.domains.verify(), reemplazar este endpoint por la consulta real.
    """
    user = request.state.user
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    result = await db.email_domains.update_one(
        {"id": domain_id, "tenant_id": user.tenant_id},
        {"$set": {
            "verification_status": "verified",
            "dkim_verified": True, "spf_verified": True, "dmarc_verified": True,
            "verified_at": now, "last_check_at": now, "degraded": False,
            "updated_at": now,
        }},
    )
    if not result.matched_count:
        raise ResourceNotFoundException()
    doc = await db.email_domains.find_one(
        {"id": domain_id}, {"_id": 0})
    return ok(public_domain(doc))


@router.delete("/domains/{domain_id}")
async def delete_domain(domain_id: str, request: Request,
                         _: object = Depends(_RBAC)):
    user = request.state.user
    db = get_db()
    # Bloquear si hay buzones referenciándolo
    mb_count = await db.email_mailboxes.count_documents({
        "tenant_id": user.tenant_id, "domain_id": domain_id,
    })
    if mb_count > 0:
        raise _val(f"No se puede eliminar: hay {mb_count} buzón(es) usando este dominio.",
                    "domain_id")
    result = await db.email_domains.delete_one(
        {"id": domain_id, "tenant_id": user.tenant_id})
    if not result.deleted_count:
        raise ResourceNotFoundException()
    return ok({"deleted": True, "id": domain_id})


# ──────────────────────────────────────────────────────────────
# MAILBOXES
# ──────────────────────────────────────────────────────────────
@router.get("/mailboxes")
async def list_mailboxes(request: Request, _: object = Depends(_RBAC),
                          client_id: str | None = Query(default=None)):
    repo = EmailMailboxRepository(tenant_id=request.state.user.tenant_id)
    q = {"client_id": client_id} if client_id is not None else {}
    items = await repo.find(q, limit=300, sort=[("created_at", -1)])
    return ok({"items": [public_mailbox(m) for m in items], "count": len(items)})


@router.post("/mailboxes", status_code=201)
async def add_mailbox(payload: MailboxCreate, request: Request,
                       _: object = Depends(_RBAC)):
    user = request.state.user
    db = get_db()
    # Validar dominio
    domain = await db.email_domains.find_one(
        {"id": payload.domain_id, "tenant_id": user.tenant_id}, {"_id": 0})
    if not domain:
        raise _val("Dominio no encontrado en este tenant.", "domain_id")
    # Validar client_id (si viene)
    if payload.client_id:
        cl = await db.clients.find_one(
            {"id": payload.client_id, "tenant_id": user.tenant_id},
            {"_id": 0, "id": 1})
        if not cl:
            raise _val("client_id no encontrado en este tenant.", "client_id")
    # Validar sender_email pertenece al dominio
    if not payload.sender_email.lower().endswith("@" + domain["domain"]):
        raise _val(
            f"sender_email debe terminar en @{domain['domain']}.",
            "sender_email")
    doc = make_mailbox_doc(
        tenant_id=user.tenant_id, domain_id=payload.domain_id,
        created_by=user.id,
        display_name=payload.display_name, sender_name=payload.sender_name,
        sender_email=payload.sender_email,
        reply_to_email=payload.reply_to_email,
        client_id=payload.client_id, api_key=payload.api_key,
        daily_send_limit=payload.daily_send_limit,
        is_default_for_tenant=payload.is_default_for_tenant,
        is_default_for_client=payload.is_default_for_client,
        workflow_types=payload.workflow_types,
    )
    # Garantizar único default
    repo = EmailMailboxRepository(tenant_id=user.tenant_id)
    if payload.is_default_for_tenant:
        await repo.clear_default_flag(scope="tenant", exclude_id=doc["id"])
    if payload.is_default_for_client and payload.client_id:
        await repo.clear_default_flag(scope="client",
                                       client_id=payload.client_id,
                                       exclude_id=doc["id"])
    await db.email_mailboxes.insert_one(doc)
    return ok(public_mailbox(doc), status_code=201)


@router.patch("/mailboxes/{mailbox_id}")
async def update_mailbox(mailbox_id: str, payload: MailboxUpdate,
                          request: Request, _: object = Depends(_RBAC)):
    user = request.state.user
    db = get_db()
    target = await db.email_mailboxes.find_one(
        {"id": mailbox_id, "tenant_id": user.tenant_id}, {"_id": 0})
    if not target:
        raise ResourceNotFoundException()
    updates: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
    for field in ("display_name", "sender_name", "reply_to_email",
                   "daily_send_limit", "is_active"):
        v = getattr(payload, field, None)
        if v is not None:
            updates[field] = v
    if payload.sender_email:
        # Validar que sigue perteneciendo al dominio
        dom = await db.email_domains.find_one(
            {"id": target["domain_id"]}, {"_id": 0, "domain": 1})
        if dom and not payload.sender_email.lower().endswith(
                "@" + dom["domain"]):
            raise _val(
                f"sender_email debe terminar en @{dom['domain']}.",
                "sender_email")
        updates["sender_email"] = payload.sender_email.lower()
    if payload.api_key:
        updates["api_key_ref"] = encrypt(payload.api_key)
        updates["api_key_last4"] = payload.api_key[-4:]
    repo = EmailMailboxRepository(tenant_id=user.tenant_id)
    if payload.is_default_for_tenant is True:
        await repo.clear_default_flag(scope="tenant", exclude_id=mailbox_id)
        updates["is_default_for_tenant"] = True
    elif payload.is_default_for_tenant is False:
        updates["is_default_for_tenant"] = False
    if payload.is_default_for_client is True and target.get("client_id"):
        await repo.clear_default_flag(scope="client",
                                       client_id=target["client_id"],
                                       exclude_id=mailbox_id)
        updates["is_default_for_client"] = True
    elif payload.is_default_for_client is False:
        updates["is_default_for_client"] = False
    await db.email_mailboxes.update_one(
        {"id": mailbox_id, "tenant_id": user.tenant_id},
        {"$set": updates},
    )
    doc = await db.email_mailboxes.find_one(
        {"id": mailbox_id}, {"_id": 0})
    return ok(public_mailbox(doc))


@router.delete("/mailboxes/{mailbox_id}")
async def delete_mailbox(mailbox_id: str, request: Request,
                          _: object = Depends(_RBAC)):
    user = request.state.user
    db = get_db()
    # No permitir borrar el último mailbox del tenant (R52)
    total = await db.email_mailboxes.count_documents(
        {"tenant_id": user.tenant_id})
    if total <= 1:
        raise _val(
            "No se puede eliminar el último buzón del tenant. Creá otro primero.",
            "mailbox_id")
    # Borrar reglas que lo referencien
    await db.email_routing.delete_many(
        {"tenant_id": user.tenant_id, "mailbox_id": mailbox_id})
    result = await db.email_mailboxes.delete_one(
        {"id": mailbox_id, "tenant_id": user.tenant_id})
    if not result.deleted_count:
        raise ResourceNotFoundException()
    return ok({"deleted": True, "id": mailbox_id})


class TestPayload(BaseModel):
    to: str = Field(min_length=3, max_length=200)


@router.post("/mailboxes/{mailbox_id}/test")
async def test_mailbox(mailbox_id: str, payload: TestPayload,
                        request: Request, _: object = Depends(_RBAC)):
    """Envía un email de prueba vía el dispatcher con `explicit_mailbox_id`."""
    user = request.state.user
    d = EmailDispatcher(user.tenant_id)
    ctx = EmailContext(
        tenant_id=user.tenant_id, workflow_type="admin_notification",
        explicit_mailbox_id=mailbox_id,
    )
    pld = EmailPayload(
        to=[payload.to],
        subject="[Prueba] Buzón configurado correctamente",
        body_html=(
            f"<div style='font-family:system-ui;padding:16px;'>"
            f"<h2 style='color:#C2410C;'>✓ Buzón funcional</h2>"
            f"<p>Este es un email de prueba enviado desde MyExcellence.</p>"
            f"<p style='font-size:11px;color:#666;'>Mailbox ID: <code>{mailbox_id[:8]}</code></p>"
            f"</div>"
        ),
        body_text="Este es un email de prueba.",
        tags={"kind": "mailbox_test"},
    )
    result = await d.send(ctx, pld)
    return ok({
        "sent": result.success,
        "error_code": result.error_code,
        "error_message": result.error_message,
        "message_id": result.provider_message_id,
        "log_id": result.log_id, "mock": result.mock,
    })


# ──────────────────────────────────────────────────────────────
# ROUTING
# ──────────────────────────────────────────────────────────────
@router.get("/routing")
async def list_routing(request: Request, _: object = Depends(_RBAC)):
    repo = EmailRoutingRepository(tenant_id=request.state.user.tenant_id)
    items = await repo.find({}, limit=500,
                             sort=[("workflow_type", 1), ("priority", -1)])
    return ok({"items": items, "count": len(items)})


@router.post("/routing", status_code=201)
async def add_routing(payload: RoutingRuleCreate, request: Request,
                       _: object = Depends(_RBAC)):
    user = request.state.user
    db = get_db()
    # Validar mailbox
    mb = await db.email_mailboxes.find_one(
        {"id": payload.mailbox_id, "tenant_id": user.tenant_id}, {"_id": 0})
    if not mb:
        raise _val("mailbox_id no encontrado en este tenant.", "mailbox_id")
    if payload.client_id:
        cl = await db.clients.find_one(
            {"id": payload.client_id, "tenant_id": user.tenant_id},
            {"_id": 0, "id": 1})
        if not cl:
            raise _val("client_id no encontrado.", "client_id")
    doc = make_routing_doc(
        tenant_id=user.tenant_id, mailbox_id=payload.mailbox_id,
        workflow_type=payload.workflow_type,
        client_id=payload.client_id, motivo_id=payload.motivo_id,
        priority=payload.priority, description=payload.description,
    )
    await db.email_routing.insert_one(doc)
    return ok(doc, status_code=201)


@router.delete("/routing/{rule_id}")
async def delete_routing(rule_id: str, request: Request,
                          _: object = Depends(_RBAC)):
    user = request.state.user
    db = get_db()
    result = await db.email_routing.delete_one(
        {"id": rule_id, "tenant_id": user.tenant_id})
    if not result.deleted_count:
        raise ResourceNotFoundException()
    return ok({"deleted": True, "id": rule_id})


# ──────────────────────────────────────────────────────────────
# EXPLAIN — depurar resolución sin enviar
# ──────────────────────────────────────────────────────────────
class ExplainPayload(BaseModel):
    workflow_type: str
    client_id: str | None = None
    motivo_id: str | None = None
    explicit_mailbox_id: str | None = None


@router.post("/explain")
async def explain_resolution(payload: ExplainPayload, request: Request,
                              _: object = Depends(_RBAC)):
    """Devuelve qué buzón resolvería el dispatcher para el contexto dado,
    junto con la cadena de decisiones (rule_id evaluadas, fallbacks)."""
    user = request.state.user
    d = EmailDispatcher(user.tenant_id)
    ctx = EmailContext(
        tenant_id=user.tenant_id,
        workflow_type=payload.workflow_type,
        client_id=payload.client_id, motivo_id=payload.motivo_id,
        explicit_mailbox_id=payload.explicit_mailbox_id,
    )
    # Resolver y armar el reporte
    rules = await d.routing.find_matching(
        workflow_type=payload.workflow_type,
        client_id=payload.client_id, motivo_id=payload.motivo_id,
    )
    resolved = await d.resolve_mailbox(ctx)
    return ok({
        "resolved_mailbox": public_mailbox(resolved) if resolved else None,
        "matched_rules": [{
            "id": r["id"], "priority": r["priority"],
            "client_id": r.get("client_id"), "motivo_id": r.get("motivo_id"),
            "mailbox_id": r["mailbox_id"],
            "description": r.get("description", ""),
        } for r in rules],
        "context": ctx.model_dump(),
    })


# ──────────────────────────────────────────────────────────────
# HEALTH — métricas (E2.5)
# ──────────────────────────────────────────────────────────────
@router.get("/health")
async def health(request: Request, _: object = Depends(_RBAC),
                  days: int = Query(default=7, ge=1, le=90)):
    user = request.state.user
    db = get_db()
    from datetime import timedelta
    end = datetime.now(timezone.utc)
    start = (end - timedelta(days=days)).isoformat()
    total = await db.email_send_log.count_documents({
        "tenant_id": user.tenant_id, "sent_at": {"$gte": start},
    })
    sent = await db.email_send_log.count_documents({
        "tenant_id": user.tenant_id, "sent_at": {"$gte": start},
        "status": "sent",
    })
    failed = await db.email_send_log.count_documents({
        "tenant_id": user.tenant_id, "sent_at": {"$gte": start},
        "status": "failed",
    })
    # Errores por código
    pipeline = [
        {"$match": {"tenant_id": user.tenant_id, "sent_at": {"$gte": start},
                     "status": "failed"}},
        {"$group": {"_id": "$error_code", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    errors = []
    async for row in db.email_send_log.aggregate(pipeline):
        errors.append({"code": row["_id"], "count": row["count"]})
    # Conteo por buzón
    pipeline_mb = [
        {"$match": {"tenant_id": user.tenant_id, "sent_at": {"$gte": start}}},
        {"$group": {"_id": "$mailbox_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    by_mailbox = []
    async for row in db.email_send_log.aggregate(pipeline_mb):
        by_mailbox.append({"mailbox_id": row["_id"], "count": row["count"]})
    return ok({
        "window_days": days,
        "total": total, "sent": sent, "failed": failed,
        "delivery_rate": (sent / total) if total > 0 else None,
        "errors_by_code": errors, "top_mailboxes": by_mailbox,
    })


@router.get("/logs")
async def list_logs(request: Request, _: object = Depends(_RBAC),
                     limit: int = Query(default=50, ge=1, le=500),
                     mailbox_id: str | None = Query(default=None),
                     status: str | None = Query(default=None)):
    repo = EmailSendLogRepository(tenant_id=request.state.user.tenant_id)
    q = {}
    if mailbox_id:
        q["mailbox_id"] = mailbox_id
    if status:
        q["status"] = status
    items = await repo.find(q, limit=limit, sort=[("sent_at", -1)])
    return ok({"items": items, "count": len(items)})
