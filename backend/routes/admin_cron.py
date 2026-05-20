"""Admin cron — PROMPT 11.5.

  GET  /api/admin/cron/status          — estado del scheduler + próximos runs
  POST /api/admin/cron/run/{job}       — fuerza la ejecución de un job
                                         (sla | inactivity | pulling | daily_summary)
"""
from __future__ import annotations
from typing import Literal

from fastapi import APIRouter, Depends, Path, Request

from core.errors import ErrorCode
from core.response import ok, fail
from middleware.rbac import require_min_role
from services import scheduler as scheduler_svc
from services.daily_summary import send_for_tenant
from services.sla_inactivity import scan_inactive_agents, scan_sla

router = APIRouter(prefix="/api/admin/cron", tags=["admin-cron"])
_RBAC = require_min_role("admin")


@router.get("/status")
async def status(_: object = Depends(_RBAC)):
    return ok(scheduler_svc.status())


JobName = Literal["sla", "inactivity", "claim_sla", "pulling", "daily_summary"]


@router.post("/run/{job}")
async def run_job(job: JobName = Path(...),
                  request: Request = None,
                  _: object = Depends(_RBAC)):
    """Fuerza la ejecución on-demand de un job. Devuelve el resultado del scan
    cuando es applicable (sla/inactivity/claim_sla), o el conteo de tenants para
    daily_summary y pulling.

    Para sla/inactivity/claim_sla ejecutamos sólo sobre el tenant del usuario
    que hace la llamada (más rápido y suficiente para diagnosticar).
    """
    user = request.state.user
    if job == "sla":
        res = await scan_sla(tenant_id=user.tenant_id)
        return ok({"job": job, "tenant_id": user.tenant_id,
                   "breaches": res.breaches, "notified": res.notified})
    if job == "inactivity":
        res = await scan_inactive_agents(tenant_id=user.tenant_id)
        return ok({"job": job, "tenant_id": user.tenant_id,
                   "inactive_agents": res.inactive_agents,
                   "notified": res.notified})
    if job == "claim_sla":
        from services.sla_inactivity import scan_claim_sla
        res = await scan_claim_sla(tenant_id=user.tenant_id)
        return ok({"job": job, "tenant_id": user.tenant_id,
                   "breaches": res.breaches, "notified": res.notified})
    if job == "daily_summary":
        s = await send_for_tenant(user.tenant_id)
        return ok({"job": job, "tenant_id": user.tenant_id,
                   "sent": s.sent, "to": s.to, "reason": s.reason,
                   "metrics": s.metrics})
    if job == "pulling":
        # Solo dispara para clientes del tenant del admin que invoca
        from core.db import get_db
        from services.ingest_service import IngestService
        db = get_db()
        clients = await db.clients.find(
            {"tenant_id": user.tenant_id, "ingest_mode": "pulling"}, {"_id": 0}
        ).to_list(length=200)
        results = []
        svc = IngestService(tenant_id=user.tenant_id)
        for c in clients:
            try:
                r = await svc.trigger_pull(client_id=c["id"])
                results.append({"client_id": c["id"], "ok": True, "result": r["result"]})
            except Exception as e:  # noqa: BLE001
                results.append({"client_id": c["id"], "ok": False, "error": str(e)})
        return ok({"job": job, "tenant_id": user.tenant_id,
                   "clients": len(clients), "results": results})
    return fail(ErrorCode.RESOURCE_NOT_FOUND, f"Unknown job: {job}")
