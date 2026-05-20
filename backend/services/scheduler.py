"""APScheduler — PROMPT 11.5.

Background worker embebido en el mismo proceso FastAPI. Cuatro jobs:

  * SLA breach scan          — cada SLA_SCAN_INTERVAL_MIN (default 5)
  * Inactivity scan (R15)     — cada INACTIVITY_SCAN_INTERVAL_MIN (default 5)
  * Pulling de clientes       — cada PULLING_INTERVAL_MIN (default 5)
  * Resumen diario por tenant — todos los días a las 09:00 UTC

Activación via env:
  - ``CRON_ENABLED=1``   (default: 0 — no arranca el scheduler en tests/CI)
  - ``MYE_SLA_MINUTES``  (umbral de breach; default 60)
  - ``MYE_INACTIVITY_MINUTES`` (umbral; default 30)
  - ``MYE_DAILY_SUMMARY_HOUR_UTC`` (default 9)
"""
from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from core.db import get_db
from core.logger import log
from services.daily_summary import send_for_all_tenants
from services.ingest_service import IngestService
from services.sla_inactivity import scan_claim_sla, scan_inactive_agents, scan_sla


# Singleton — evita doble arranque
_scheduler: Optional[AsyncIOScheduler] = None


def _int_env(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except ValueError:
        return default


def _enabled() -> bool:
    return os.environ.get("CRON_ENABLED", "0") == "1"


# ───────────────────────── Job bodies ──────────────────────────────────
async def _job_sla() -> None:
    db = get_db()
    minutes = _int_env("MYE_SLA_MINUTES", 60)
    tenants = await db.tenants.find({"status": "active"}, {"_id": 0}).to_list(length=500)
    for t in tenants:
        try:
            await scan_sla(tenant_id=t["id"], sla_minutes=minutes)
        except Exception:  # noqa: BLE001
            log.exception("sla_job_tenant_failed", extra={"context": {"tenant_id": t["id"]}})


async def _job_inactivity() -> None:
    db = get_db()
    minutes = _int_env("MYE_INACTIVITY_MINUTES", 30)
    tenants = await db.tenants.find({"status": "active"}, {"_id": 0}).to_list(length=500)
    for t in tenants:
        try:
            await scan_inactive_agents(tenant_id=t["id"], threshold_minutes=minutes)
        except Exception:  # noqa: BLE001
            log.exception("inactivity_job_tenant_failed",
                          extra={"context": {"tenant_id": t["id"]}})


async def _job_claim_sla() -> None:
    """P1.1 — SLA específico de reclamos (umbrales por estado)."""
    db = get_db()
    tenants = await db.tenants.find({"status": "active"}, {"_id": 0}).to_list(length=500)
    for t in tenants:
        try:
            await scan_claim_sla(tenant_id=t["id"])
        except Exception:  # noqa: BLE001
            log.exception("claim_sla_job_tenant_failed",
                          extra={"context": {"tenant_id": t["id"]}})


async def _job_pulling() -> None:
    """Para cada cliente con ingest_mode=pulling, ejecuta el adapter pertinente.

    Routal real: `list_recent_plans` → `list_stops_in_plan` → para cada stop
    con `external_id`, llama IngestService.process_event para pasar por todo
    el pipeline (CAE normalize, ticket creation, R02 terminal protection,
    webhooks salientes).

    Otros carriers todavía mockeados: log "pull_attempt".
    """
    db = get_db()
    cursor = db.clients.find({"ingest_mode": "pulling"}, {"_id": 0})
    async for client in cursor:
        try:
            await _pull_client(client)
        except Exception:  # noqa: BLE001
            log.exception("pulling_job_client_failed",
                          extra={"context": {"client_id": client.get("id")}})


async def _pull_client(client: dict) -> None:
    """Decide el adapter por carrier_code preferido del cliente y dispara
    el pull. Hoy soporta Routal real; otros carriers caen al stub legacy.
    """
    tenant_id = client["tenant_id"]
    client_id = client["id"]
    preferred_carrier = (client.get("preferred_carrier_code") or "").lower()
    if preferred_carrier == "routal":
        await _pull_routal(tenant_id=tenant_id, client_id=client_id,
                           limit_plans=int(client.get("pulling_max_plans", 5)))
        return
    # Fallback legacy — aún no hay adapter real para este carrier
    svc = IngestService(tenant_id=tenant_id)
    await svc.trigger_pull(client_id=client_id)


async def _pull_routal(*, tenant_id: str, client_id: str,
                        limit_plans: int = 5) -> dict:
    """Recorre los últimos N plans en CADA project_id configurado del cliente,
    normaliza cada stop y dispara el pipeline de ingest. Soporta el modelo
    1:N de Cubbo (un ApiKey por cliente, N proyectos por cliente).

    Resolución de credenciales:
      1. ``clients.carriers.routal`` (SaaS por-cliente — preferido)
      2. ``.env`` ROUTAL_API_KEY/ROUTAL_PROJECT_ID — fallback legacy
    """
    from services.cae.adapters.routal import RoutalAdapter
    from services.ingest_service import IngestService
    from services.carrier_config_resolver import resolve_carrier_config

    cfg = await resolve_carrier_config(
        tenant_id=tenant_id, client_id=client_id, code="routal")
    if cfg and cfg.get("api_key"):
        adapter = RoutalAdapter(
            api_key=cfg["api_key"],
            project_ids=cfg.get("project_ids") or [],
            base_url=cfg.get("base_url"),
        )
        config_source = cfg.get("config_source", "unknown")
    else:
        # legacy env-based fallback (single project for the whole platform)
        adapter = RoutalAdapter()
        config_source = "env"
        if not await adapter.validate_config():
            log.warning("routal_pull_skipped_no_config", extra={"context": {
                "tenant_id": tenant_id, "client_id": client_id,
            }})
            return {"skipped": "no_config"}

    svc = IngestService(tenant_id=tenant_id)
    processed = 0
    skipped = 0
    errors = 0
    plans_total = 0
    for project_id in adapter.project_ids:
        try:
            plans = await adapter.list_recent_plans(project_id=project_id,
                                                     limit=limit_plans)
        except Exception:  # noqa: BLE001
            log.exception("routal_pull_plans_failed", extra={"context": {
                "tenant_id": tenant_id, "client_id": client_id,
                "project_id": project_id,
            }})
            continue
        plans_total += len(plans)
        for plan in plans:
            plan_id = plan.get("id")
            if not plan_id:
                continue
            try:
                stops = await adapter.list_stops_in_plan(plan_id)
            except Exception:  # noqa: BLE001
                log.exception("routal_pull_stops_failed", extra={"context": {
                    "tenant_id": tenant_id, "client_id": client_id,
                    "project_id": project_id, "plan_id": plan_id,
                }})
                continue
            for stop in stops:
                external_id = stop.get("external_id")
                if not external_id:
                    skipped += 1
                    continue
                try:
                    # Tag the stop with its origin project so the raw_payload
                    # carries it through to guias.carrier_meta.
                    stop["_routal_project_id"] = project_id
                    event = adapter._stop_to_event(external_id, stop)
                    await svc.process_event(
                        client_id=client_id,
                        tracking_id=external_id,
                        carrier_code="routal",
                        carrier_status=event.raw_code,
                        carrier_status_description=event.raw_description,
                        raw_code=event.raw_code,
                        api_version=event.api_version,
                        event_at=event.event_at.isoformat(),
                        raw_payload=event.raw_payload,
                        source="pulling",
                        carrier_meta={"routal_project_id": project_id,
                                      "plan_id": plan_id,
                                      "stop_id": stop.get("id")},
                    )
                    processed += 1
                except Exception:  # noqa: BLE001
                    errors += 1
                    log.exception("routal_pull_stop_failed", extra={"context": {
                        "tenant_id": tenant_id, "client_id": client_id,
                        "project_id": project_id,
                        "external_id": external_id, "plan_id": plan_id,
                    }})
    log.info("routal_pull_complete", extra={"context": {
        "tenant_id": tenant_id, "client_id": client_id,
        "config_source": config_source,
        "projects": adapter.project_ids,
        "plans": plans_total, "processed": processed,
        "skipped": skipped, "errors": errors,
    }})
    return {"processed": processed, "skipped": skipped, "errors": errors,
            "plans": plans_total, "projects": adapter.project_ids,
            "config_source": config_source}


async def _job_daily_summary() -> None:
    try:
        results = await send_for_all_tenants()
        log.info("daily_summary_job_complete", extra={"context": {
            "tenants": len(results),
            "sent": sum(1 for r in results if r["sent"]),
        }})
    except Exception:  # noqa: BLE001
        log.exception("daily_summary_job_failed")


async def _job_webhook_worker() -> None:
    """PROMPT 39 V3 — procesa hasta 100 jobs vencidos por tick (cada 30s)."""
    try:
        from services.webhooks.dispatcher import worker_tick
        res = await worker_tick(batch=100)
        if res.get("processed"):
            log.info("webhook_worker_tick", extra={"context": res})
    except Exception:  # noqa: BLE001
        log.exception("webhook_worker_tick_failed")


async def _job_escalation() -> None:
    """Iter54 P1.3 — escala tickets sin respuesta del cliente tras N
    notificaciones + grace window."""
    from services.escalation import scan_unresponsive_tickets
    db = get_db()
    max_notifs = _int_env("MYE_ESCALATION_MAX_NOTIFICATIONS", 3)
    grace_hours = _int_env("MYE_ESCALATION_GRACE_HOURS", 48)
    tenants = await db.tenants.find({"status": "active"}, {"_id": 0}).to_list(length=500)
    for t in tenants:
        try:
            await scan_unresponsive_tickets(
                tenant_id=t["id"],
                max_notifications=max_notifs, grace_hours=grace_hours,
            )
        except Exception:  # noqa: BLE001
            log.exception("escalation_job_tenant_failed",
                          extra={"context": {"tenant_id": t["id"]}})


# ───────────────────────── Lifecycle ───────────────────────────────────
def start() -> Optional[AsyncIOScheduler]:
    """Arranca el scheduler si CRON_ENABLED=1. Idempotente."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    if not _enabled():
        log.info("cron_disabled", extra={"context": {"reason": "CRON_ENABLED!=1"}})
        return None

    sla_every = _int_env("SLA_SCAN_INTERVAL_MIN", 5)
    inactivity_every = _int_env("INACTIVITY_SCAN_INTERVAL_MIN", 5)
    claim_sla_every = _int_env("CLAIM_SLA_SCAN_INTERVAL_MIN", 30)
    pulling_every = _int_env("PULLING_INTERVAL_MIN", 5)
    daily_hour = _int_env("MYE_DAILY_SUMMARY_HOUR_UTC", 9)

    sched = AsyncIOScheduler(timezone="UTC")
    sched.add_job(_job_sla, IntervalTrigger(minutes=sla_every),
                  id="sla_scan", coalesce=True, max_instances=1)
    sched.add_job(_job_inactivity, IntervalTrigger(minutes=inactivity_every),
                  id="inactivity_scan", coalesce=True, max_instances=1)
    sched.add_job(_job_claim_sla, IntervalTrigger(minutes=claim_sla_every),
                  id="claim_sla_scan", coalesce=True, max_instances=1)
    sched.add_job(_job_pulling, IntervalTrigger(minutes=pulling_every),
                  id="pulling", coalesce=True, max_instances=1)
    sched.add_job(_job_daily_summary, CronTrigger(hour=daily_hour, minute=0),
                  id="daily_summary", coalesce=True, max_instances=1)
    webhook_every = _int_env("WEBHOOK_WORKER_INTERVAL_SEC", 30)
    sched.add_job(_job_webhook_worker, IntervalTrigger(seconds=webhook_every),
                  id="webhook_worker", coalesce=True, max_instances=1)
    escalation_every = _int_env("ESCALATION_INTERVAL_MIN", 60)
    sched.add_job(_job_escalation, IntervalTrigger(minutes=escalation_every),
                  id="escalation", coalesce=True, max_instances=1)
    sched.start()
    _scheduler = sched
    log.info("cron_started", extra={"context": {
        "sla_every": sla_every, "inactivity_every": inactivity_every,
        "claim_sla_every": claim_sla_every,
        "pulling_every": pulling_every, "daily_hour_utc": daily_hour,
        "webhook_every_sec": webhook_every,
        "escalation_every_min": escalation_every,
    }})
    return sched


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            log.exception("cron_shutdown_failed")
        _scheduler = None


def status() -> dict:
    """Devuelve el estado actual de los jobs."""
    if _scheduler is None:
        return {"running": False, "jobs": [], "enabled_env": _enabled()}
    jobs = []
    for j in _scheduler.get_jobs():
        jobs.append({
            "id": j.id,
            "trigger": str(j.trigger),
            "next_run_time": j.next_run_time.isoformat() if j.next_run_time else None,
        })
    return {
        "running": _scheduler.running,
        "jobs": jobs,
        "enabled_env": _enabled(),
        "now": datetime.now(timezone.utc).isoformat(),
    }


# Job dispatch table (used by the admin "force run" endpoint)
JOBS = {
    "sla": _job_sla,
    "inactivity": _job_inactivity,
    "claim_sla": _job_claim_sla,
    "pulling": _job_pulling,
    "daily_summary": _job_daily_summary,
    "webhook_worker": _job_webhook_worker,
    "escalation": _job_escalation,
}
