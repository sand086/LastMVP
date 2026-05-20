"""Tickets read API — agent panel (PROMPT 08) implements the full CRUD.

For now we expose enough to verify WorkflowEngine + CAE wiring end-to-end:
  GET /api/admin/tickets               list (filter optional)
  GET /api/admin/tickets/{id}          detail + timeline events
"""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from core.db import get_db
from core.errors import ResourceNotFoundException
from core.response import ok
from middleware.rbac import require_min_role
from repositories.tickets import TicketRepository

router = APIRouter(prefix="/api/admin/tickets", tags=["admin-tickets"])

_RBAC = require_min_role("supervisor")


def _t(request: Request) -> str:
    return request.state.user.tenant_id


@router.get("")
async def list_tickets(
    request: Request,
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: object = Depends(_RBAC),
):
    repo = TicketRepository(tenant_id=_t(request))
    query = {}
    if status:
        query["status"] = status
    items = await repo.find(query, sort=[("created_at", -1)], limit=limit)
    return ok({"items": items, "count": len(items)})


@router.get("/{ticket_id}")
async def ticket_detail(ticket_id: str, request: Request, _: object = Depends(_RBAC)):
    repo = TicketRepository(tenant_id=_t(request))
    ticket = await repo.find_one({"id": ticket_id})
    if not ticket:
        raise ResourceNotFoundException()
    timeline_cursor = get_db().timeline_events.find(
        {"tenant_id": _t(request), "ticket_id": ticket_id},
        {"_id": 0},
    ).sort("created_at", 1).limit(500)
    timeline = await timeline_cursor.to_list(length=500)
    guia = await get_db().guias.find_one(
        {"tenant_id": _t(request), "id": ticket["guia_id"]},
        {"_id": 0, "raw_payload": 0},
    ) if ticket.get("guia_id") else None
    # PROMPT 13 — surface the active reclamo so the UI can switch the CTA
    active_claim = await get_db().claims.find_one(
        {"tenant_id": _t(request), "ticket_id": ticket_id, "is_terminal": False},
        {"_id": 0},
    )
    return ok({"ticket": ticket, "timeline": timeline, "guia": guia,
               "active_claim": active_claim})
