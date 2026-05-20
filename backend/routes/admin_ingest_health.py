"""Iter58 — Health endpoint para ingesta.

  GET /api/admin/ingest/health

Devuelve por cliente del tenant:
  - total_guias
  - status_breakdown: {delivered, in_transit, returned, exception, ...}
  - tickets_open / tickets_total
  - last_ingest_at (max(guias.last_ingest_at))
  - last_pull_at — última invocación de _pull_range (de logs si existiera)
  - carrier_code

Útil para identificar clientes vencidos (sin pull reciente) o con muchas
incidencias abiertas. RBAC: admin+.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from core.db import get_db
from core.response import ok
from middleware.rbac import require_min_role

router = APIRouter(prefix="/api/admin/ingest", tags=["admin-ingest-health"])

_RBAC = require_min_role("admin")


@router.get("/health")
async def ingest_health(request: Request, _: object = Depends(_RBAC)):
    db = get_db()
    tenant_id = request.state.user.tenant_id

    # 1) Lista de clientes del tenant
    clients = await db.clients.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "id": 1, "name": 1, "slug": 1, "carrier": 1,
         "carriers": 1, "ingest_mode": 1, "pulling_freq_min": 1},
    ).to_list(length=500)

    # 2) Distribución de status x cliente (aggregation)
    breakdown_pipeline = [
        {"$match": {"tenant_id": tenant_id, "client_id": {"$ne": None}}},
        {"$group": {
            "_id": {"client_id": "$client_id",
                    "internal_status": "$internal_status"},
            "count": {"$sum": 1},
            "last_ingest_at": {"$max": "$last_ingest_at"},
        }},
    ]
    by_client: dict[str, dict] = {}
    async for row in db.guias.aggregate(breakdown_pipeline):
        cid = row["_id"]["client_id"]
        status = row["_id"]["internal_status"] or "unknown"
        slot = by_client.setdefault(cid, {
            "status": {}, "total": 0, "last_ingest_at": None,
        })
        slot["status"][status] = row["count"]
        slot["total"] += row["count"]
        if row.get("last_ingest_at"):
            cur = slot.get("last_ingest_at")
            if not cur or row["last_ingest_at"] > cur:
                slot["last_ingest_at"] = row["last_ingest_at"]

    # 3) Tickets por cliente (abiertos vs total)
    tickets_pipeline = [
        {"$match": {"tenant_id": tenant_id, "client_id": {"$ne": None}}},
        {"$group": {
            "_id": "$client_id",
            "total": {"$sum": 1},
            "open": {"$sum": {"$cond": [
                {"$in": ["$status", ["pending", "in_progress",
                                      "waiting_client", "waiting_carrier",
                                      "escalated", "claim"]]},
                1, 0]}},
        }},
    ]
    tickets_by_client: dict[str, dict] = {}
    async for row in db.tickets.aggregate(tickets_pipeline):
        tickets_by_client[row["_id"]] = {
            "total": row["total"], "open": row["open"],
        }

    # 4) Construcción final
    items = []
    for c in clients:
        breakdown = by_client.get(c["id"], {})
        tickets = tickets_by_client.get(c["id"], {"total": 0, "open": 0})
        carrier_code = (c.get("carrier") or
                        next(iter((c.get("carriers") or {}).keys()), None)
                        or "—")
        items.append({
            "client_id": c["id"],
            "client_name": c["name"],
            "client_slug": c.get("slug"),
            "carrier_code": carrier_code,
            "ingest_mode": c.get("ingest_mode") or "—",
            "pulling_freq_min": c.get("pulling_freq_min"),
            "total_guias": breakdown.get("total", 0),
            "status_breakdown": breakdown.get("status", {}),
            "last_ingest_at": breakdown.get("last_ingest_at"),
            "tickets_total": tickets["total"],
            "tickets_open": tickets["open"],
        })
    # Sort: más guías primero
    items.sort(key=lambda x: -x["total_guias"])

    totals = {
        "clients": len(items),
        "with_data": sum(1 for i in items if i["total_guias"] > 0),
        "total_guias": sum(i["total_guias"] for i in items),
        "tickets_open": sum(i["tickets_open"] for i in items),
    }
    return ok({"items": items, "totals": totals})
