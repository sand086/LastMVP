"""Admin email templates — CRUD por tenant (PROMPT 11 backlog)."""
from __future__ import annotations
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from core.errors import ResourceNotFoundException
from core.response import fail, ok
from middleware.rbac import require_min_role
from services.email_templates import (
    SUPPORTED_KEYS, TEMPLATE_VARIABLES,
    delete_template, list_templates, render_string,
    upsert_template,
)


router = APIRouter(prefix="/api/admin/email-templates", tags=["admin-email-templates"])
_RBAC = require_min_role("admin")


class TemplatePayload(BaseModel):
    key: str = Field(min_length=1, max_length=50)
    subject: str = Field(min_length=1, max_length=200)
    html_body: str = Field(min_length=1, max_length=20_000)
    text_body: str = Field(default="", max_length=10_000)


class PreviewPayload(BaseModel):
    subject: str = ""
    html_body: str = ""
    text_body: str = ""
    ctx: dict = Field(default_factory=dict)


@router.get("")
async def list_all(request: Request, _: object = Depends(_RBAC)):
    user = request.state.user
    items = await list_templates(tenant_id=user.tenant_id)
    return ok({
        "items": items, "count": len(items),
        "supported_keys": sorted(SUPPORTED_KEYS),
        "variables": TEMPLATE_VARIABLES,
    })


@router.put("")
async def upsert(payload: TemplatePayload, request: Request,
                 _: object = Depends(_RBAC)):
    user = request.state.user
    if payload.key not in SUPPORTED_KEYS:
        return fail("VALIDATION_FAILED",
                    f"Clave '{payload.key}' no soportada. Permitidas: {sorted(SUPPORTED_KEYS)}",
                    field="key")
    doc = await upsert_template(
        tenant_id=user.tenant_id, key=payload.key,
        subject=payload.subject, html_body=payload.html_body,
        text_body=payload.text_body, updated_by=user.id,
    )
    return ok(doc)


@router.delete("/{key}")
async def delete_one(key: str, request: Request, _: object = Depends(_RBAC)):
    user = request.state.user
    n = await delete_template(tenant_id=user.tenant_id, key=key)
    if n == 0:
        raise ResourceNotFoundException()
    return ok({"deleted": True, "key": key})


@router.post("/preview")
async def preview(payload: PreviewPayload, request: Request,
                   _: object = Depends(_RBAC)):
    """Preview con sustitución de variables sin guardar nada."""
    ctx = {
        "recipient_name": "María García",
        "ticket_id": "abcd1234",
        "tracking_id": "TRK-DEMO-001",
        "message": "Tu envío presenta un retraso debido a un evento meteorológico.",
        "cta_url": "https://app.myexcellence.com/reclamos/abcd1234",
        "cta_label": "Ver reclamo",
        "tenant_name": "Demo Tenant",
        **payload.ctx,
    }
    return ok({
        "subject": render_string(payload.subject, ctx),
        "html": render_string(payload.html_body, ctx),
        "text": render_string(payload.text_body, ctx),
        "ctx_used": ctx,
    })
