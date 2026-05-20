"""Admin email settings — credenciales Resend por tenant.

iter46 · Multi-tenant SaaS — cada tenant configura su propia API key,
sender identity y reply-to default desde la UX. La API key se guarda
encriptada con Fernet (`core.crypto`).

Endpoints:
  GET   /api/admin/email-settings              — vista pública (sin API key)
  PUT   /api/admin/email-settings              — upsert
  POST  /api/admin/email-settings/test         — envía email de prueba
  DELETE /api/admin/email-settings             — desactiva (status=disabled)
"""
from __future__ import annotations
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator

from core.errors import MyEException, ErrorCode
from core.response import ok
from middleware.rbac import require_min_role
from services import tenant_email_settings as ts
from services.notification_service import send_email, render_test_email


router = APIRouter(prefix="/api/admin/email-settings",
                   tags=["admin-email-settings"])
_RBAC = require_min_role("admin")

_EMAIL_RX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class EmailSettingsPayload(BaseModel):
    sender_email: str = Field(min_length=3, max_length=200)
    sender_name: str = Field(min_length=1, max_length=100)
    api_key: str | None = Field(default=None, max_length=200,
                                 description="Si es None, conserva la existente")
    reply_to_default: str | None = Field(default=None, max_length=200)
    status: str = Field(default="active")

    @field_validator("sender_email", "reply_to_default")
    @classmethod
    def _validate_email(cls, v):
        if v in (None, ""):
            return v
        if not _EMAIL_RX.match(v):
            raise ValueError("Email inválido")
        return v

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v):
        if v not in ("active", "disabled"):
            raise ValueError("status debe ser 'active' o 'disabled'")
        return v


class TestPayload(BaseModel):
    to: str = Field(min_length=3, max_length=200)

    @field_validator("to")
    @classmethod
    def _validate_email(cls, v):
        if not _EMAIL_RX.match(v):
            raise ValueError("Email inválido")
        return v


@router.get("")
async def get(request: Request, _: object = Depends(_RBAC)):
    user = request.state.user
    return ok(await ts.get_public_view(user.tenant_id))


@router.put("")
async def upsert(payload: EmailSettingsPayload, request: Request,
                 _: object = Depends(_RBAC)):
    user = request.state.user
    view = await ts.upsert(
        tenant_id=user.tenant_id,
        actor_id=user.id,
        sender_email=payload.sender_email,
        sender_name=payload.sender_name,
        api_key=payload.api_key or None,
        reply_to_default=payload.reply_to_default or None,
        status=payload.status,
    )
    return ok(view)


@router.delete("")
async def disable(request: Request, _: object = Depends(_RBAC)):
    """Soft-disable — mantiene la API key encriptada por si la quieren reactivar.
    Mientras `status=disabled`, send_email cae a las env globales.
    """
    user = request.state.user
    from core.db import get_db
    await get_db()[ts.COLLECTION].update_one(
        {"tenant_id": user.tenant_id},
        {"$set": {"status": "disabled",
                  "updated_at": datetime.now(timezone.utc).isoformat(),
                  "updated_by": user.id}},
    )
    return ok(await ts.get_public_view(user.tenant_id))


@router.post("/test")
async def test_send(payload: TestPayload, request: Request,
                     _: object = Depends(_RBAC)):
    """Envía un email de prueba usando la config del tenant.

    Si el tenant aún no tiene config (o está disabled), usa las env globales —
    útil para validar el flujo end-to-end sin tener Resend del cliente listo.
    """
    user = request.state.user
    settings = await ts.get_settings(user.tenant_id) or {}
    if settings.get("status") != "active" or not settings.get("api_key_ref"):
        raise MyEException(
            ErrorCode.VALIDATION_FAILED,
            "Configurá una API key activa antes de enviar un email de prueba.",
            field="api_key",
        )
    html, text = render_test_email(recipient_name=user.name or user.email)
    result = await send_email(
        to=payload.to,
        subject="[Prueba] Configuración de email — MyExcellence",
        html=html, text=text,
        tags={"kind": "email_settings_test"},
        tenant_id=user.tenant_id,
    )
    await ts.record_test_result(
        tenant_id=user.tenant_id, ok=result.ok, error=result.reason,
    )
    return ok({
        "sent": result.ok, "mock": result.mock,
        "id": result.id, "error": result.reason,
    })
