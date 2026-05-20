"""Iter50 — Endpoint admin para limpieza retroactiva de encoding (`\\uFFFD`).
Iter52 — También endpoint para reconciliar tickets cuyas guías ya están
        entregadas (auto-resolve retroactivo).

  POST /api/admin/maintenance/fix-encoding?dry_run=true|false
  POST /api/admin/maintenance/reconcile-delivered-tickets?dry_run=true|false

RBAC: root_dev|superadmin. Scope: tenant del caller.
"""
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request

from core.db import get_db
from core.response import ok
from middleware.rbac import require_min_role
from repositories.tickets import TicketRepository, TERMINAL_TICKET_STATUSES
from scripts.fix_encoding_legacy import fix_encoding_in_db
from services.cae_seed import seed_cae_defaults
from services.escalation import scan_unresponsive_tickets
from services.soluciones_seed import seed_soluciones

router = APIRouter(prefix="/api/admin/maintenance", tags=["admin-maintenance"])

_RBAC = require_min_role("superadmin")


@router.post("/fix-encoding")
async def fix_encoding(
    request: Request,
    dry_run: bool = Query(default=True),
    _: object = Depends(_RBAC),
):
    """Repara strings con `\\uFFFD` (char `�`) en guias/tickets del tenant.

    - `dry_run=true` (default): solo cuenta y devuelve samples (máx 10).
    - `dry_run=false`: persiste las reparaciones (irreversible).

    Auditoría: las samples devueltas permiten al admin validar el resultado
    antes de aplicar.
    """
    tenant_id = request.state.user.tenant_id
    stats = await fix_encoding_in_db(dry_run=dry_run, tenant_id=tenant_id)
    return ok(stats)


@router.post("/reconcile-delivered-tickets")
async def reconcile_delivered_tickets(
    request: Request,
    dry_run: bool = Query(default=True),
    _: object = Depends(_RBAC),
):
    """Iter52 — Auto-resolve retroactivo de tickets cuyas guías ya están
    `delivered`/`is_terminal=True` pero quedaron con ticket abierto.

    Causa común: ingest CSV con status "Entregado" antes de que el
    WorkflowEngine soportara el fallback `internal_status` (iter52). Tras el
    fix, este endpoint barre y cierra los tickets que ya deberían estarlo.

    Devuelve: {scanned, resolved, samples: [{ticket_id, guia_id, tracking_id}]}
    """
    tenant_id = request.state.user.tenant_id
    actor_id = request.state.user.id
    db = get_db()

    # Guías ya entregadas en este tenant.
    guia_cursor = db.guias.find(
        {"tenant_id": tenant_id,
         "$or": [{"is_terminal": True},
                 {"internal_status": "delivered"}]},
        {"_id": 0, "id": 1, "tracking_id": 1, "internal_status": 1},
    )
    delivered_guia_ids: dict[str, str] = {}
    async for g in guia_cursor:
        if (g.get("internal_status") or "").lower() == "delivered":
            delivered_guia_ids[g["id"]] = g.get("tracking_id") or ""

    stats: dict = {"scanned": 0, "resolved": 0, "samples": []}
    if not delivered_guia_ids:
        return ok(stats)

    # Tickets aún abiertos asociados a esas guías.
    open_cursor = db.tickets.find(
        {"tenant_id": tenant_id,
         "guia_id": {"$in": list(delivered_guia_ids.keys())},
         "status": {"$nin": list(TERMINAL_TICKET_STATUSES)}},
        {"_id": 0, "id": 1, "guia_id": 1, "status": 1},
    )
    repo = TicketRepository(tenant_id=tenant_id)
    async for t in open_cursor:
        stats["scanned"] += 1
        if len(stats["samples"]) < 10:
            stats["samples"].append({
                "ticket_id": t["id"],
                "guia_id": t.get("guia_id"),
                "tracking_id": delivered_guia_ids.get(t.get("guia_id"), ""),
                "previous_status": t.get("status"),
            })
        if not dry_run:
            await repo.change_status(
                t["id"], "resolved",
                actor_id=actor_id,
                reason="Reconciliación retroactiva — guía entregada (iter52)",
            )
            stats["resolved"] += 1
    if dry_run:
        # En dry_run reportamos cuántos SE resolverían
        stats["resolved"] = stats["scanned"]
    stats["timestamp"] = datetime.now(timezone.utc).isoformat()
    return ok(stats)


@router.post("/seed-cae-defaults")
async def seed_cae(request: Request, _: object = Depends(_RBAC)):
    """Iter54 — Siembra el catálogo CAE con los strings del Layout V2
    (Entregado, En tránsito, Rechazado, Destinatario ausente, etc.) para los
    4 carriers principales (fedex, dhl, redpack, estafeta). Idempotente.
    """
    tenant_id = request.state.user.tenant_id
    stats = await seed_cae_defaults(tenant_id=tenant_id, scope="tenant")
    return ok(stats)


@router.post("/seed-soluciones")
async def seed_sol(request: Request, _: object = Depends(_RBAC)):
    """Iter54 — Siembra las soluciones estándar derivadas del documento del
    cliente: contactar destinatario, solicitar referencias, aviso final,
    retorno automático. Idempotente."""
    tenant_id = request.state.user.tenant_id
    stats = await seed_soluciones(tenant_id=tenant_id)
    return ok(stats)


@router.post("/run-escalation")
async def run_escalation(
    request: Request,
    dry_run: bool = Query(default=True),
    max_notifications: int = Query(default=3, ge=1, le=10),
    grace_hours: int = Query(default=48, ge=1, le=720),
    _: object = Depends(_RBAC),
):
    """Iter54 — Dispara manualmente el scan de tickets sin respuesta del
    cliente. En cron normal corre cada `ESCALATION_INTERVAL_MIN` (60min)."""
    tenant_id = request.state.user.tenant_id
    res = await scan_unresponsive_tickets(
        tenant_id=tenant_id,
        max_notifications=max_notifications,
        grace_hours=grace_hours,
        dry_run=dry_run,
    )
    return ok({
        "scanned": res.scanned, "escalated": res.escalated,
        "skipped": res.skipped, "dry_run": dry_run,
    })

