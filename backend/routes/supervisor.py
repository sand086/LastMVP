"""Supervisor routes — PROMPT 09 (Torre de Control)."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query, Request

from core.db import get_db
from core.response import ok
from middleware.rbac import require_min_role
from repositories.tickets import TERMINAL_TICKET_STATUSES

router = APIRouter(prefix="/api/supervisor", tags=["supervisor"])

_RBAC = require_min_role("supervisor")

# R15 — pause on espera_* states (the agent is waiting on someone else)
_WAITING_STATUSES = {"waiting_client", "waiting_carrier"}


def _t(request: Request) -> str:
    return request.state.user.tenant_id


@router.get("/tickets-by-agent")
async def tickets_by_agent(request: Request, _: object = Depends(_RBAC)):
    db = get_db()
    tenant_id = _t(request)
    pipeline = [
        {"$match": {"tenant_id": tenant_id,
                    "status": {"$nin": list(TERMINAL_TICKET_STATUSES)}}},
        {"$group": {
            "_id": "$assigned_agent_id",
            "open": {"$sum": 1},
            "waiting": {"$sum": {"$cond": [{"$in": ["$status", list(_WAITING_STATUSES)]}, 1, 0]}},
            "in_progress": {"$sum": {"$cond": [{"$eq": ["$status", "in_progress"]}, 1, 0]}},
            "pending": {"$sum": {"$cond": [{"$eq": ["$status", "pending"]}, 1, 0]}},
            "claim": {"$sum": {"$cond": [{"$eq": ["$status", "claim"]}, 1, 0]}},
        }},
    ]
    rows = await db.tickets.aggregate(pipeline).to_list(length=200)
    # Resolve agent names
    agents = await db.users.find(
        {"tenant_id": tenant_id, "role": "agent"},
        {"_id": 0, "password_hash": 0},
    ).to_list(length=500)
    agent_map = {a["id"]: a for a in agents}

    items = []
    for r in rows:
        aid = r["_id"]
        if aid is None:
            items.append({
                "agent_id": None,
                "name": "Sin asignar",
                "email": None,
                "open": r["open"], "waiting": r["waiting"],
                "in_progress": r["in_progress"], "pending": r["pending"],
                "claim": r["claim"],
            })
            continue
        a = agent_map.get(aid)
        items.append({
            "agent_id": aid,
            "name": a.get("name") if a else "—",
            "email": a.get("email") if a else None,
            "open": r["open"], "waiting": r["waiting"],
            "in_progress": r["in_progress"], "pending": r["pending"],
            "claim": r["claim"],
        })

    # Surface agents with zero open work too
    counted = {r["_id"] for r in rows}
    for a in agents:
        if a["id"] not in counted:
            items.append({
                "agent_id": a["id"], "name": a.get("name"), "email": a.get("email"),
                "open": 0, "waiting": 0, "in_progress": 0, "pending": 0, "claim": 0,
            })
    return ok({"items": items, "count": len(items)})


@router.get("/inactive-agents")
async def inactive_agents(
    request: Request,
    threshold_minutes: int = Query(default=30, ge=1, le=480),
    _: object = Depends(_RBAC),
):
    """R15 — agents with no ticket update in > threshold but with open non-waiting tickets."""
    db = get_db()
    tenant_id = _t(request)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)).isoformat()
    pipeline = [
        {"$match": {"tenant_id": tenant_id,
                    "status": {"$nin": list(TERMINAL_TICKET_STATUSES) + list(_WAITING_STATUSES)},
                    "assigned_agent_id": {"$ne": None}}},
        {"$group": {
            "_id": "$assigned_agent_id",
            "last_update": {"$max": "$updated_at"},
            "open_actionable": {"$sum": 1},
        }},
        {"$match": {"last_update": {"$lt": cutoff}, "open_actionable": {"$gt": 0}}},
    ]
    rows = await db.tickets.aggregate(pipeline).to_list(length=200)
    agents = await db.users.find(
        {"tenant_id": tenant_id, "id": {"$in": [r["_id"] for r in rows]}},
        {"_id": 0, "password_hash": 0},
    ).to_list(length=500)
    amap = {a["id"]: a for a in agents}
    return ok({
        "threshold_minutes": threshold_minutes,
        "items": [
            {
                "agent_id": r["_id"],
                "name": amap.get(r["_id"], {}).get("name", "—"),
                "email": amap.get(r["_id"], {}).get("email"),
                "open_actionable": r["open_actionable"],
                "last_update": r["last_update"],
            }
            for r in rows
        ],
        "count": len(rows),
    })
