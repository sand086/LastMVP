"""Saved filters CRUD endpoints (PROMPT 03 backlog)."""
from __future__ import annotations
from typing import Literal

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, Field

from core.errors import ResourceNotFoundException
from core.response import ok
from middleware.rbac import require_min_role
from repositories.saved_filters import SavedFilterRepository


router = APIRouter(prefix="/api/saved-filters", tags=["saved-filters"])
_RBAC = require_min_role("agent")


class SavedFilterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    scope: Literal["agent_queue", "admin_tickets", "claims"] = "agent_queue"
    filters: dict = Field(default_factory=dict)


@router.get("")
async def list_filters(request: Request, _: object = Depends(_RBAC)):
    user = request.state.user
    repo = SavedFilterRepository(tenant_id=user.tenant_id)
    items = await repo.list_for_user(user.id)
    return ok({"items": items, "count": len(items)})


@router.post("", status_code=201)
async def create_filter(body: SavedFilterCreate, request: Request,
                         _: object = Depends(_RBAC)):
    user = request.state.user
    repo = SavedFilterRepository(tenant_id=user.tenant_id)
    doc = await repo.create(user_id=user.id, name=body.name, scope=body.scope,
                             filters=body.filters)
    return ok(doc, status_code=201)


@router.delete("/{filter_id}")
async def delete_filter(filter_id: str = Path(...), request: Request = None,
                         _: object = Depends(_RBAC)):
    user = request.state.user
    repo = SavedFilterRepository(tenant_id=user.tenant_id)
    n = await repo.delete(filter_id, user.id)
    if n == 0:
        raise ResourceNotFoundException()
    return ok({"deleted": True, "id": filter_id})
