"""Dashboard KPIs — PROMPT 10 (sec 6.3 of MYEXCELLENCE.md).

Five must-have KPIs:
  1. open_tickets         — currently open across the tenant
  2. resolved_today       — tickets resolved/closed today (UTC)
  3. automation_rate      — % of tickets in last 30d with solucion + can_automate=true
  4. avg_resolution_minutes — mean (resolved_at - created_at) on resolved tickets
  5. backlog_aged         — count of open tickets with last_update > 24h
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Request

from core.db import get_db
from core.response import ok
from middleware.rbac import require_min_role
from repositories.tickets import TERMINAL_TICKET_STATUSES

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_RBAC = require_min_role("supervisor")


def _t(request: Request) -> str:
    return request.state.user.tenant_id


@router.get("/kpis")
async def kpis(request: Request, _: object = Depends(_RBAC)):
    db = get_db()
    tenant_id = _t(request)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    backlog_cutoff = (now - timedelta(hours=24)).isoformat()

    open_tickets = await db.tickets.count_documents({
        "tenant_id": tenant_id,
        "status": {"$nin": list(TERMINAL_TICKET_STATUSES)},
    })
    resolved_today = await db.tickets.count_documents({
        "tenant_id": tenant_id,
        "status": {"$in": list(TERMINAL_TICKET_STATUSES)},
        "updated_at": {"$gte": today_start},
    })
    backlog_aged = await db.tickets.count_documents({
        "tenant_id": tenant_id,
        "status": {"$nin": list(TERMINAL_TICKET_STATUSES)},
        "updated_at": {"$lt": backlog_cutoff},
    })
    # Automation rate (tickets in last 30d with solucion_id NOT null)
    last30 = await db.tickets.count_documents({
        "tenant_id": tenant_id,
        "created_at": {"$gte": thirty_days_ago},
    })
    last30_automatable = await db.tickets.count_documents({
        "tenant_id": tenant_id,
        "created_at": {"$gte": thirty_days_ago},
        "solucion_id": {"$ne": None},
    })
    automation_rate = round(last30_automatable / last30 * 100, 1) if last30 else 0.0
    return ok({
        "open_tickets": open_tickets,
        "resolved_today": resolved_today,
        "backlog_aged_24h": backlog_aged,
        "automation_rate_30d": automation_rate,
        "tickets_30d": last30,
    })


@router.get("/incidents-by-type")
async def incidents_by_type(request: Request, _: object = Depends(_RBAC)):
    db = get_db()
    tenant_id = _t(request)
    pipeline = [
        {"$match": {"tenant_id": tenant_id, "incident_type": {"$ne": None}}},
        {"$group": {"_id": "$incident_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 12},
    ]
    rows = await db.tickets.aggregate(pipeline).to_list(length=20)
    items = [{"incident_type": r["_id"], "count": r["count"]} for r in rows]
    return ok({"items": items, "count": len(items)})


@router.get("/throughput-7d")
async def throughput_7d(request: Request, _: object = Depends(_RBAC)):
    """Daily count of tickets created in the last 7 days (string-prefix match on ISO date)."""
    db = get_db()
    tenant_id = _t(request)
    now = datetime.now(timezone.utc)
    days = []
    for offset in range(6, -1, -1):
        d = (now - timedelta(days=offset)).date().isoformat()
        days.append(d)
    out = []
    for d in days:
        count = await db.tickets.count_documents({
            "tenant_id": tenant_id,
            "created_at": {"$gte": d + "T00:00:00", "$lt": d + "T23:59:59"},
        })
        out.append({"date": d, "count": count})
    return ok({"items": out, "count": len(out)})


# ────────────────────── Claims KPIs (P1.3 / P1.4) ───────────────────────
TERMINAL_CLAIM = ["conciliado", "desistido"]


@router.get("/claims-open")
async def claims_open(request: Request, _: object = Depends(_RBAC)):
    """KPI específico de reclamos: abiertos por estado + indemnizaciones."""
    db = get_db()
    tenant_id = _t(request)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    backlog_cutoff = (now - timedelta(hours=24)).isoformat()

    open_total = await db.claims.count_documents({
        "tenant_id": tenant_id, "is_terminal": False,
    })
    in_dictamen = await db.claims.count_documents({
        "tenant_id": tenant_id, "estado": "en_dictamen_carrier",
    })
    in_dictamen_aging = await db.claims.count_documents({
        "tenant_id": tenant_id, "estado": "en_dictamen_carrier",
        "updated_at": {"$lt": backlog_cutoff},
    })
    conciliated_today = await db.claims.count_documents({
        "tenant_id": tenant_id, "estado": "conciliado",
        "updated_at": {"$gte": today_start},
    })
    sla_breaches_24h = await db.claim_events.count_documents({
        "tenant_id": tenant_id, "event_type": "claim_sla_breach",
        "created_at": {"$gte": (now - timedelta(hours=24)).isoformat()},
    })

    by_estado_pipeline = [
        {"$match": {"tenant_id": tenant_id, "is_terminal": False}},
        {"$group": {"_id": "$estado", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    by_estado_rows = await db.claims.aggregate(by_estado_pipeline).to_list(length=20)
    by_estado = [{"estado": r["_id"], "count": r["count"]} for r in by_estado_rows]
    return ok({
        "open_total": open_total,
        "in_dictamen": in_dictamen,
        "in_dictamen_aging_24h": in_dictamen_aging,
        "conciliated_today": conciliated_today,
        "sla_breaches_24h": sla_breaches_24h,
        "by_estado": by_estado,
    })


@router.get("/report/must-have")
async def report_must_have(
    request: Request,
    days: int = 7,
    _: object = Depends(_RBAC),
):
    """P1.4 — Reporte must-have del periodo (7 días por defecto)."""
    db = get_db()
    tenant_id = _t(request)
    now = datetime.now(timezone.utc)
    period_start = (now - timedelta(days=max(1, min(days, 90)))).isoformat()

    # Tickets section
    tickets_total = await db.tickets.count_documents({
        "tenant_id": tenant_id, "created_at": {"$gte": period_start},
    })
    tickets_resolved = await db.tickets.count_documents({
        "tenant_id": tenant_id,
        "status": {"$in": list(TERMINAL_TICKET_STATUSES)},
        "updated_at": {"$gte": period_start},
    })
    automations_executed = await db.timeline_events.count_documents({
        "tenant_id": tenant_id, "event_type": "automation_executed",
        "created_at": {"$gte": period_start},
    })

    # Claims section (P1.4)
    claims_promoted = await db.claims.count_documents({
        "tenant_id": tenant_id, "promoted_at": {"$gte": period_start},
    })
    claims_open = await db.claims.count_documents({
        "tenant_id": tenant_id, "is_terminal": False,
    })
    claims_conciliated = await db.claims.count_documents({
        "tenant_id": tenant_id, "estado": "conciliado",
        "updated_at": {"$gte": period_start},
    })
    claims_rejected = await db.claims.count_documents({
        "tenant_id": tenant_id, "estado": "rechazado_carrier",
        "updated_at": {"$gte": period_start},
    })

    # Sum monto reclamado / aprobado / conciliado del periodo
    money_pipeline = [
        {"$match": {"tenant_id": tenant_id, "promoted_at": {"$gte": period_start}}},
        {"$group": {"_id": None,
                    "monto_reclamado": {"$sum": "$monto_reclamado"}}},
    ]
    money_row = await db.claims.aggregate(money_pipeline).to_list(length=1)
    monto_reclamado_total = money_row[0]["monto_reclamado"] if money_row else 0

    indem_pipeline = [
        {"$match": {"tenant_id": tenant_id, "created_at": {"$gte": period_start}}},
        {"$group": {"_id": None,
                    "monto_aprobado": {"$sum": "$monto_aprobado"},
                    "monto_conciliado": {"$sum": "$monto_conciliado"}}},
    ]
    indem_row = await db.claim_indemnizations.aggregate(indem_pipeline).to_list(length=1)
    monto_aprobado = indem_row[0]["monto_aprobado"] if indem_row else 0
    monto_conciliado = indem_row[0]["monto_conciliado"] if indem_row else 0

    by_tipo_pipeline = [
        {"$match": {"tenant_id": tenant_id, "promoted_at": {"$gte": period_start}}},
        {"$group": {"_id": "$tipo_dano", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    by_tipo_rows = await db.claims.aggregate(by_tipo_pipeline).to_list(length=20)

    return ok({
        "period": {"days": days, "from": period_start, "to": now.isoformat()},
        "tickets": {
            "total": tickets_total, "resolved": tickets_resolved,
            "automations_executed": automations_executed,
        },
        "claims": {
            "promoted": claims_promoted, "open": claims_open,
            "conciliated": claims_conciliated, "rejected": claims_rejected,
            "monto_reclamado_total": monto_reclamado_total,
            "monto_aprobado_total": monto_aprobado,
            "monto_conciliado_total": monto_conciliado,
            "by_tipo_dano": [{"tipo_dano": r["_id"], "count": r["count"]}
                             for r in by_tipo_rows],
        },
    })
