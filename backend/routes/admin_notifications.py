"""Admin notifications — PROMPT 11.

  GET  /api/admin/notifications/config   — estado de la config de notif (sin secretos)
  POST /api/admin/notifications/test     — envía email de prueba.

Bundle A · FIX-A3 (Mayo 2026): el endpoint /test valida el dominio del
destinatario contra una whitelist (global + por tenant) y exige
``confirmed_external=true`` cuando el dominio NO está en la whitelist.
Cuando ese flag llega `true`, registra un audit event para trazabilidad.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr

from core.config import RESEND_API_KEY, SENDER_EMAIL
from core.db import get_db
from core.errors import ErrorCode
from core.response import fail, ok
from core.uuid import new_id
from middleware.rbac import require_min_role
from routes.admin_test_domains import (
    GLOBAL_TEST_DOMAINS, extract_domain, is_whitelisted,
)
from services.notification_service import render_test_email, send_email

router = APIRouter(prefix="/api/admin/notifications", tags=["admin-notifications"])
_RBAC = require_min_role("admin")


class TestEmailRequest(BaseModel):
    to: Optional[EmailStr] = None  # default: usuario autenticado
    confirmed_external: bool = False


@router.get("/config")
async def config(request: Request, _: object = Depends(_RBAC)):
    """Devuelve el estado de la configuración de notificaciones (sin secretos)."""
    return ok({
        "resend_configured": bool(RESEND_API_KEY),
        "sender_email": SENDER_EMAIL,
        "channels_available": ["email", "whatsapp"],
        "test_whitelist_globals": list(GLOBAL_TEST_DOMAINS),
    })


@router.post("/test")
async def send_test(payload: TestEmailRequest, request: Request,
                    _: object = Depends(_RBAC)):
    """Envía un email de prueba para validar la integración con Resend.

    Bundle A · FIX-A3: si el dominio del destinatario NO está en la
    whitelist (global + tenant) y ``confirmed_external != true``, el
    endpoint responde 422 EXTERNAL_DOMAIN_REQUIRES_CONFIRMATION. Si el
    front confirmó (modal de aviso), registramos audit event.
    """
    user = request.state.user
    to_email = (payload.to or user.email)
    domain = extract_domain(to_email)
    if not domain:
        return fail(ErrorCode.VALIDATION_FAILED,
                    "Email malformado.", field="to")

    is_external = not await is_whitelisted(domain, tenant_id=user.tenant_id)
    if is_external and not payload.confirmed_external:
        return fail(
            ErrorCode.VALIDATION_FAILED,
            (f"El destinatario '{to_email}' parece externo. "
             "Confirma desde la UI antes de enviar el mensaje de prueba."),
            field="to",
            extra_errors=[{
                "code": "EXTERNAL_DOMAIN_REQUIRES_CONFIRMATION",
                "message": f"Dominio '{domain}' no está en la whitelist.",
                "field": "to",
            }],
        )

    audit_event_id: Optional[str] = None
    if is_external and payload.confirmed_external:
        audit_event_id = new_id()
        try:
            await get_db().user_audit_log.insert_one({
                "id": audit_event_id,
                "tenant_id": user.tenant_id,
                "actor_id": user.id,
                "actor_email": user.email,
                "actor_role": user.role,
                "action": "notif.test_external",
                "target_id": user.id,
                "target_email": to_email,
                "before": None,
                "after": {"recipient": to_email, "domain": domain},
                "ip": request.client.host if request.client else None,
                "user_agent": (request.headers.get("user-agent") or "")[:200] or None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:  # noqa: BLE001
            audit_event_id = None  # nunca bloquear el envío por fallo de audit

    html, text = render_test_email(recipient_name=user.name or "Admin")
    result = await send_email(
        to=to_email,
        subject="[MyExcellence] Email de prueba",
        html=html, text=text,
        tags={"kind": "test", "tenant_id": user.tenant_id[:8]},
    )
    return ok({
        "to": to_email,
        "result": result.to_dict(),
        "external_domain": is_external,
        "audit_event_id": audit_event_id,
    }, status_code=200 if result.ok else 502)
