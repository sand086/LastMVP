"""CAE Admin routes — minimal scaffolding (PROMPT_06 implements the full UI).

Only endpoints required for the bootstrap to be smoke-testable:
  - GET /api/admin/cae/unmapped         : list unmapped codes
  - GET /api/admin/cae/catalog          : list current mappings
  - GET /api/admin/cae/audit-log        : history (append-only)
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, Request

from core.db import get_db
from core.response import ok
from middleware.rbac import require_min_role

router = APIRouter(prefix="/api/admin/cae", tags=["cae-admin"])

# Iter59 — Permitimos admin+ acceso a CAE para gestión de homologaciones
# por tenant. Anteriormente sólo root_dev|superadmin (sec 14.6) — los
# admins de cliente necesitan poder remapear códigos sin escalar.
_RBAC = require_min_role("admin")


@router.get("/unmapped")
async def unmapped(request: Request, _user=Depends(_RBAC)):
    db = get_db()
    cursor = db.cae_unmapped_codes.find({}, {"_id": 0}).sort("last_seen", -1).limit(200)
    items = await cursor.to_list(length=200)
    return ok({"items": items, "count": len(items)})


@router.get("/catalog")
async def catalog(request: Request, _user=Depends(_RBAC)):
    db = get_db()
    user = request.state.user
    # Catalog rows can be tenant-specific OR global (tenant_id=None)
    cursor = db.carrier_status_catalog.find(
        {"$or": [{"tenant_id": user.tenant_id}, {"tenant_id": None}], "active": True},
        {"_id": 0},
    ).sort("carrier_id", 1).limit(500)
    items = await cursor.to_list(length=500)
    return ok({"items": items, "count": len(items)})


@router.get("/audit-log")
async def audit_log(request: Request, _user=Depends(_RBAC)):
    db = get_db()
    user = request.state.user
    cursor = db.cae_audit_log.find(
        {"tenant_id": user.tenant_id}, {"_id": 0}
    ).sort("created_at", -1).limit(200)
    items = await cursor.to_list(length=200)
    return ok({"items": items, "count": len(items)})
