"""Admin seed endpoints — restringido a root_dev|superadmin para no
contaminar producción accidentalmente. Útil para QA y demos al cliente.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, Request

from core.response import ok
from middleware.rbac import require_role
from seeds.demo_claims import seed_demo_claims


router = APIRouter(prefix="/api/admin/seed", tags=["admin-seed"])
_RBAC = require_role("root_dev", "superadmin")


@router.post("/demo-claims")
async def seed_demo_claims_endpoint(request: Request, _: object = Depends(_RBAC)):
    """Provisiona 3 reclamos demo en el tenant del usuario (idempotente)."""
    user = request.state.user
    db = request.app.state.db if hasattr(request.app.state, "db") else None  # noqa: F841
    # Resolver slug del tenant
    from core.db import get_db
    tenant = await get_db().tenants.find_one(
        {"id": user.tenant_id}, {"_id": 0, "slug": 1},
    )
    result = await seed_demo_claims(tenant_slug=tenant["slug"] if tenant else "myexcellence")
    return ok(result)
