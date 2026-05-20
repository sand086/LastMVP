"""Inbox routes — PROMPT 13 P1.2.

  GET   /api/inbox                 listar notificaciones del usuario auth
  GET   /api/inbox/unread-count    badge counter
  POST  /api/inbox/{id}/read       marca como leída
  POST  /api/inbox/read-all        marca todas como leídas
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, Query, Request

from core.errors import ResourceNotFoundException
from core.response import ok
from middleware.rbac import require_min_role
from repositories.inbox import InboxRepository

router = APIRouter(prefix="/api/inbox", tags=["inbox"])
_RBAC = require_min_role("agent")


@router.get("")
async def list_inbox(request: Request, only_unread: bool = Query(default=False),
                     limit: int = Query(default=30, ge=1, le=200),
                     _: object = Depends(_RBAC)):
    user = request.state.user
    repo = InboxRepository(tenant_id=user.tenant_id)
    items = await repo.list_for(user_id=user.id, only_unread=only_unread, limit=limit)
    return ok({"items": items, "count": len(items)})


@router.get("/unread-count")
async def unread_count(request: Request, _: object = Depends(_RBAC)):
    user = request.state.user
    repo = InboxRepository(tenant_id=user.tenant_id)
    n = await repo.count_unread(user_id=user.id)
    return ok({"unread": n})


@router.post("/{notif_id}/read")
async def mark_one_read(notif_id: str, request: Request, _: object = Depends(_RBAC)):
    user = request.state.user
    repo = InboxRepository(tenant_id=user.tenant_id)
    if not await repo.mark_read(user_id=user.id, notif_id=notif_id):
        raise ResourceNotFoundException()
    return ok({"id": notif_id, "read": True})


@router.post("/read-all")
async def mark_all_read(request: Request, _: object = Depends(_RBAC)):
    user = request.state.user
    repo = InboxRepository(tenant_id=user.tenant_id)
    n = await repo.mark_all_read(user_id=user.id)
    return ok({"updated": n})
