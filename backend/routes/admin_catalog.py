"""Catalog admin — Motivos + Soluciones (PROMPT 03)."""
from __future__ import annotations
from fastapi import APIRouter, Depends, Request

from core.errors import ResourceNotFoundException
from core.response import ok
from middleware.rbac import require_min_role
from models.catalog import MotivoCreate, MotivoUpdate, SolucionCreate, SolucionUpdate
from repositories.catalog import MotivoRepository, SolucionRepository

router = APIRouter(prefix="/api/admin", tags=["admin-catalog"])

_RBAC = require_min_role("admin")


def _tenant(request: Request) -> str:
    return request.state.user.tenant_id


# ----- Motivos -----------------------------------------------------------
@router.get("/motivos")
async def list_motivos(request: Request, _: object = Depends(_RBAC)):
    repo = MotivoRepository(tenant_id=_tenant(request))
    items = await repo.find({}, sort=[("code", 1)], limit=500)
    return ok({"items": items, "count": len(items)})


@router.post("/motivos", status_code=201)
async def create_motivo(payload: MotivoCreate, request: Request, _: object = Depends(_RBAC)):
    repo = MotivoRepository(tenant_id=_tenant(request))
    existing = await repo.by_code(payload.code)
    if existing:
        return ok(existing, status_code=200)
    doc = await repo.create(
        code=payload.code, name=payload.name,
        restricted=payload.restricted, active=payload.active,
    )
    return ok(doc, status_code=201)


@router.patch("/motivos/{motivo_id}")
async def update_motivo(motivo_id: str, payload: MotivoUpdate, request: Request,
                        _: object = Depends(_RBAC)):
    repo = MotivoRepository(tenant_id=_tenant(request))
    if not await repo.find_one({"id": motivo_id}):
        raise ResourceNotFoundException()
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if updates:
        await repo.update_one({"id": motivo_id}, updates)
    # Bundle B · R50 — invalidar proyecciones de tickets afectados
    from services.rules.cache import invalidate_tickets_for_motivo
    await invalidate_tickets_for_motivo(
        tenant_id=_tenant(request), motivo_id=motivo_id,
    )
    return ok(await repo.find_one({"id": motivo_id}))


# ----- Soluciones --------------------------------------------------------
@router.get("/soluciones")
async def list_soluciones(request: Request, _: object = Depends(_RBAC)):
    repo = SolucionRepository(tenant_id=_tenant(request))
    items = await repo.find({}, sort=[("created_at", 1)], limit=500)
    return ok({"items": items, "count": len(items)})


@router.post("/soluciones", status_code=201)
async def create_solucion(payload: SolucionCreate, request: Request, _: object = Depends(_RBAC)):
    tenant_id = _tenant(request)
    motivos = MotivoRepository(tenant_id=tenant_id)
    if not await motivos.find_one({"id": payload.motivo_id}):
        raise ResourceNotFoundException("Motivo no encontrado en este tenant.")
    repo = SolucionRepository(tenant_id=tenant_id)
    doc = await repo.create(
        motivo_id=payload.motivo_id,
        name=payload.name,
        steps=[s.model_dump() for s in payload.steps],
        template_email=payload.template_email,
        template_wa=payload.template_wa,
        automatable=payload.automatable,
    )
    return ok(doc, status_code=201)


@router.patch("/soluciones/{solucion_id}")
async def update_solucion(solucion_id: str, payload: SolucionUpdate, request: Request,
                          _: object = Depends(_RBAC)):
    repo = SolucionRepository(tenant_id=_tenant(request))
    if not await repo.find_one({"id": solucion_id}):
        raise ResourceNotFoundException()
    updates = payload.model_dump(exclude_none=True)
    if "steps" in updates and updates["steps"] is not None:
        updates["steps"] = [s if isinstance(s, dict) else s.model_dump() for s in updates["steps"]]
    if updates:
        await repo.update_one({"id": solucion_id}, updates)
    return ok(await repo.find_one({"id": solucion_id}))
