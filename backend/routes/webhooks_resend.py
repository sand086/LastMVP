"""Iter55 — Resend inbound webhook (Phase 3 Multi-Buzon).

Cuando un cliente responde a un correo enviado desde MyExcellence, Resend
puede entregarnos ese mensaje vía webhook si el dominio tiene MX inbound.
Aquí registramos la respuesta como evento de timeline en el ticket original
y **reseteamos** `client_notifications_count` para que el cron `escalation`
NO retorne a origen un ticket donde el cliente sí contestó.

Match del ticket:
  1. Por `tag.ticket_id` (idempotente, preferido — los emails que enviamos
     ya llevan este tag).
  2. Por `In-Reply-To` / `References` matchea `message_id` en `email_send_log`.
  3. Fallback: por subject que contenga tracking_id conocido en el tenant.

Seguridad:
  - Si `RESEND_WEBHOOK_SECRET` está seteado en `.env`, validamos signature
    via header `svix-signature` (Resend usa Svix). Sin secret en dev, no
    valida (modo permissive para testing).
"""
from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, Request

from core.db import get_db
from core.errors import ErrorCode, MyEException
from core.logger import log
from core.response import fail, ok

router = APIRouter(prefix="/api/webhooks/resend", tags=["webhooks-resend"])


def _verify_signature(raw_body: bytes, signature_header: str | None) -> None:
    """Valida la firma Svix si hay secret en env. Lanza si inválida."""
    secret = os.environ.get("RESEND_WEBHOOK_SECRET")
    if not secret:
        return  # dev mode — sin validación
    if not signature_header:
        raise MyEException(
            ErrorCode.UNAUTHORIZED, "Missing svix-signature header")
    # Implementación mínima de validación Svix HMAC SHA256.
    # En prod recomendado: usar la lib `svix` oficial.
    try:
        import hmac
        import hashlib
        import base64
        # Svix format: "v1,<base64>"
        parts = dict(p.split("=", 1) for p in signature_header.split(",")
                     if "=" in p) if "=" in signature_header else {}
        sig_b64 = parts.get("v1") or signature_header.split(",")[-1]
        expected = base64.b64encode(
            hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()
        ).decode()
        if not hmac.compare_digest(sig_b64.strip(), expected):
            raise MyEException(ErrorCode.UNAUTHORIZED, "Bad signature")
    except MyEException:
        raise
    except Exception:  # noqa: BLE001
        log.exception("resend_signature_check_failed")
        raise MyEException(ErrorCode.UNAUTHORIZED, "Signature validation error")


async def _resolve_ticket_from_payload(payload: dict) -> tuple[str | None, str | None]:
    """Match heuristic. Devuelve (ticket_id, tenant_id) o (None, None)."""
    db = get_db()
    data = payload.get("data") or payload  # Resend wraps in `data`

    # 1) Tag ticket_id (preferred — short prefix 8 chars)
    tags = data.get("tags") or {}
    ticket_prefix = None
    if isinstance(tags, dict):
        ticket_prefix = tags.get("ticket_id")
    elif isinstance(tags, list):
        for t in tags:
            if isinstance(t, dict) and t.get("name") == "ticket_id":
                ticket_prefix = t.get("value")
                break
    if ticket_prefix:
        t = await db.tickets.find_one(
            {"id": {"$regex": f"^{ticket_prefix}"}}, {"_id": 0, "id": 1, "tenant_id": 1},
        )
        if t:
            return t["id"], t["tenant_id"]

    # 2) In-Reply-To matchea email_send_log.message_id
    in_reply_to = (data.get("in_reply_to") or data.get("headers", {}).get("in-reply-to") or "")
    if in_reply_to:
        log_doc = await db.email_send_log.find_one(
            {"message_id": in_reply_to.strip("<> ")},
            {"_id": 0, "ticket_id": 1, "tenant_id": 1},
        )
        if log_doc and log_doc.get("ticket_id"):
            return log_doc["ticket_id"], log_doc["tenant_id"]

    # 3) Subject contiene tracking_id
    subject = data.get("subject") or ""
    if subject:
        # Buscar tokens alfanuméricos largos (típicos tracking IDs)
        import re
        for token in re.findall(r"[A-Z0-9]{6,}", subject.upper()):
            g = await db.guias.find_one(
                {"tracking_id": token}, {"_id": 0, "id": 1, "tenant_id": 1},
            )
            if g:
                t = await db.tickets.find_one(
                    {"guia_id": g["id"]}, {"_id": 0, "id": 1, "tenant_id": 1},
                )
                if t:
                    return t["id"], t["tenant_id"]

    return None, None


@router.post("/inbound")
async def resend_inbound(
    request: Request,
    svix_signature: str | None = Header(default=None),
):
    """Recibe replies del cliente. Si matchea un ticket existente, registra
    timeline `client_reply` y resetea `client_notifications_count=0`.

    Eventos Resend que procesamos: `email.received`, `inbound.received`.
    Cualquier otro (delivered, bounced, etc.) se loggea y se descarta.
    """
    raw_body = await request.body()
    try:
        _verify_signature(raw_body, svix_signature)
    except MyEException as e:
        return fail(e.error_code, e.message)

    try:
        import json
        payload = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        return fail(ErrorCode.VALIDATION_FAILED, "Invalid JSON")

    event_type = payload.get("type") or payload.get("event") or "unknown"
    if event_type not in ("email.received", "inbound.received",
                          "email.delivered", "email.bounced", "email.complained"):
        log.info("resend_event_ignored", extra={"context": {"event": event_type}})
        return ok({"action": "ignored", "event": event_type})

    # Solo reseteamos contador para eventos de respuesta entrante
    if event_type in ("email.delivered", "email.bounced", "email.complained"):
        # Logueamos para auditoría pero no reseteamos contador
        log.info("resend_outbound_event",
                 extra={"context": {"event": event_type}})
        return ok({"action": "logged", "event": event_type})

    ticket_id, tenant_id = await _resolve_ticket_from_payload(payload)
    if not ticket_id:
        log.info("resend_inbound_no_match",
                 extra={"context": {"event": event_type,
                                    "subject": (payload.get("data") or {}).get("subject", "")[:100]}})
        return ok({"action": "no_match"})

    db = get_db()
    from_email = ((payload.get("data") or {}).get("from") or "").lower()
    snippet = ((payload.get("data") or {}).get("text") or
               (payload.get("data") or {}).get("html") or "")[:500]

    # Reset contador + log timeline
    now = datetime.now(timezone.utc).isoformat()
    await db.tickets.update_one(
        {"id": ticket_id, "tenant_id": tenant_id},
        {"$set": {
            "client_notifications_count": 0,
            "last_client_reply_at": now,
            "status": "in_progress",  # vuelve a accionable
            "updated_at": now,
        }},
    )
    await db.timeline_events.insert_one({
        "id": _new_id(),
        "tenant_id": tenant_id,
        "ticket_id": ticket_id,
        "event_type": "client_reply",
        "actor_type": "external",
        "actor_id": None,
        "channel": "email",
        "payload": {
            "from": from_email,
            "snippet": snippet[:300],
            "received_at": now,
        },
        "created_at": now,
    })
    log.info("resend_inbound_matched", extra={"context": {
        "ticket_id": ticket_id, "tenant_id": tenant_id, "from": from_email[:80],
    }})
    return ok({"action": "matched", "ticket_id": ticket_id})


def _new_id() -> str:
    from core.uuid import new_id
    return new_id()
