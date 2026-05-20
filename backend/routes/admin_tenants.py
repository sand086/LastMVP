"""Tenants admin — root_dev only (cross-tenant by nature)."""
from __future__ import annotations
from fastapi import APIRouter, Depends

from core.errors import ResourceNotFoundException
from core.response import ok
from middleware.rbac import require_role
from models.admin import TenantCreate, TenantUpdate
from repositories.tenants import TenantRepository

router = APIRouter(prefix="/api/admin/tenants", tags=["admin-tenants"])

_RBAC = require_role("root_dev")


@router.get("")
async def list_tenants(_: object = Depends(_RBAC)):
    repo = TenantRepository()
    cursor = repo.col.find({}, {"_id": 0}).sort("created_at", 1).limit(500)
    items = await cursor.to_list(length=500)
    return ok({"items": items, "count": len(items)})


@router.post("", status_code=201)
async def create_tenant(payload: TenantCreate, _: object = Depends(_RBAC)):
    repo = TenantRepository()
    existing = await repo.by_slug(payload.slug)
    if existing:
        return ok({"id": existing["id"], "duplicate": True}, status_code=200)
    doc = await repo.create(name=payload.name, slug=payload.slug, status=payload.status)
    return ok(doc, status_code=201)


@router.patch("/{tenant_id}")
async def update_tenant(tenant_id: str, payload: TenantUpdate, _: object = Depends(_RBAC)):
    repo = TenantRepository()
    found = await repo.col.find_one({"id": tenant_id}, {"_id": 0})
    if not found:
        raise ResourceNotFoundException()
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if updates:
        await repo.col.update_one({"id": tenant_id}, {"$set": updates})
    refreshed = await repo.col.find_one({"id": tenant_id}, {"_id": 0})
    return ok(refreshed)
