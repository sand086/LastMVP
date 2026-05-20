"""Bundle B · R50 · Debug endpoint para proyecciones de reglas.

Solo accesible a `root_dev`. Útil en producción para diagnosticar "¿por
qué este botón aparece deshabilitado?".

GET /api/admin/rules/explain?ticket_id=...
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, Query, Request

from core.response import ok
from middleware.rbac import require_min_role
from services.rules.projection_service import projection_service

router = APIRouter(prefix="/api/admin/rules", tags=["admin-rules"])
_RBAC = require_min_role("root_dev")


@router.get("/explain")
async def explain(
    request: Request,
    ticket_id: str = Query(min_length=8, max_length=64),
    _: object = Depends(_RBAC),
):
    user = request.state.user
    data = await projection_service.explain_for_ticket(
        tenant_id=user.tenant_id, ticket_id=ticket_id,
        user_id=user.id, user_role=user.role,
    )
    return ok(data)
