"""Automation permissions admin (PROMPT 03 + R03)."""
from __future__ import annotations
from fastapi import APIRouter, Depends, Query, Request

from core.errors import ResourceNotFoundException
from core.response import ok
from middleware.rbac import require_min_role
from models.catalog import AutomationPermissionUpsert
from repositories.automation_permissions import AutomationPermissionRepository
from repositories.clients import ClientRepository
from repositories.catalog import SolucionRepository
from services.automation_check import can_automate

router = APIRouter(prefix="/api/admin/automation-permissions", tags=["admin-automation"])

# Sec 6.4: enabling automation requires admin or coordinator
_RBAC = require_min_role("coordinator")


def _tenant(request: Request) -> str:
    return request.state.user.tenant_id


@router.get("")
async def list_permissions(request: Request, client_id: str = Query(...),
                           _: object = Depends(_RBAC)):
    tenant_id = _tenant(request)
    # Validate client belongs to caller's tenant — R08
    if not await ClientRepository(tenant_id=tenant_id).find_one({"id": client_id}):
        raise ResourceNotFoundException("Cliente no encontrado en este tenant.")
    repo = AutomationPermissionRepository(tenant_id=tenant_id)
    items = await repo.find_for_client(client_id)
    return ok({"items": items, "count": len(items), "client_id": client_id})


@router.put("")
async def upsert_permission(payload: AutomationPermissionUpsert, request: Request,
                            _: object = Depends(_RBAC)):
    tenant_id = _tenant(request)
    # Validate both refs belong to caller's tenant
    if not await ClientRepository(tenant_id=tenant_id).find_one({"id": payload.client_id}):
        raise ResourceNotFoundException("Cliente no encontrado en este tenant.")
    if not await SolucionRepository(tenant_id=tenant_id).find_one({"id": payload.solucion_id}):
        raise ResourceNotFoundException("Solución no encontrada en este tenant.")
    repo = AutomationPermissionRepository(tenant_id=tenant_id)
    row = await repo.upsert(
        client_id=payload.client_id,
        solucion_id=payload.solucion_id,
        channel=payload.channel,
        allowed=payload.allowed,
    )
    # Bundle B · R50 — invalidar proyecciones de tickets del cliente afectado
    from services.rules.cache import invalidate_tickets_for_client
    await invalidate_tickets_for_client(
        tenant_id=tenant_id, client_id=payload.client_id,
    )
    return ok(row)


@router.get("/check")
async def check_permission(
    request: Request,
    client_id: str = Query(...),
    solucion_id: str = Query(...),
    channel: str = Query(...),
    _: object = Depends(_RBAC),
):
    """Diagnostic endpoint — exposes the same R03 evaluation used by AutomationService."""
    decision = await can_automate(
        tenant_id=_tenant(request),
        client_id=client_id,
        solucion_id=solucion_id,
        channel=channel,
    )
    return ok({"can_automate": decision.can_automate, "reason": decision.reason})
