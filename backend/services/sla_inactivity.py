"""SLA + Inactivity scanners — PROMPT 11.5 (Árbol #4 del WorkflowEngine).

Estos servicios son **read-only sobre tickets** salvo en una sola escritura:
  - registran un timeline_event (`sla_breach` | `agent_inactive`) cuando detectan
    un caso, y NO lo vuelven a registrar dentro de la misma ventana
    (deduplicación via la marca de tiempo del último evento).

El cron real vive en ``services/scheduler.py``; este módulo expone la lógica
pura para que tests + endpoints admin puedan dispararla on-demand.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from core.db import get_db
from core.logger import log
from repositories.tickets import TERMINAL_TICKET_STATUSES

# R15 — espera_* pausa el reloj
WAITING_STATUSES = {"waiting_client", "waiting_carrier"}


@dataclass
class SlaResult:
    breaches: int
    notified: int  # tickets que recibieron timeline_event nuevo


@dataclass
class InactivityResult:
    inactive_agents: int
    notified: int


@dataclass
class ClaimSlaResult:
    breaches: int
    notified: int


# Default thresholds (hours) — pueden override-se via sla_config doc del tenant.
DEFAULT_CLAIM_SLA_HOURS: dict[str, int] = {
    "promovido":            48,
    "expediente_en_armado": 72,
    "enviado_carrier":      24,
    "en_dictamen_carrier":  240,  # 10 días
    "aprobado_carrier":     48,
    "rechazado_carrier":    72,
    "en_conciliacion":      120,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ───────────────────────── SLA scanner ─────────────────────────────────
async def scan_sla(*, tenant_id: str, sla_minutes: int = 60) -> SlaResult:
    """Detecta tickets sin avance > sla_minutes y emite ``sla_breach`` en
    su timeline. Si el último evento del ticket ya es ``sla_breach`` con
    cutoff vigente, se omite (no spam).

    Aplica solo a tickets en estados accionables (no terminales, no waiting_*).
    """
    db = get_db()
    now = _now()
    cutoff_iso = _iso(now - timedelta(minutes=sla_minutes))
    query = {
        "tenant_id": tenant_id,
        "status": {"$nin": list(TERMINAL_TICKET_STATUSES) + list(WAITING_STATUSES)},
        "updated_at": {"$lt": cutoff_iso},
    }
    breaches = await db.tickets.find(query, {"_id": 0}).to_list(length=2000)
    notified = 0
    for t in breaches:
        # Skip si ya hay un sla_breach posterior al cutoff
        last = await db.timeline_events.find_one(
            {"tenant_id": tenant_id, "ticket_id": t["id"], "event_type": "sla_breach"},
            {"_id": 0}, sort=[("created_at", -1)],
        )
        if last and last["created_at"] >= cutoff_iso:
            continue
        await db.timeline_events.insert_one({
            "id": _new_id(),
            "tenant_id": tenant_id,
            "ticket_id": t["id"],
            "event_type": "sla_breach",
            "actor_type": "system",
            "actor_id": None,
            "channel": "internal",
            "payload": {
                "sla_minutes": sla_minutes,
                "current_status": t["status"],
                "last_update": t["updated_at"],
                "ticket_age_minutes": int((now - _parse(t["updated_at"])).total_seconds() // 60),
            },
            "created_at": _iso(now),
        })
        notified += 1
    log.info("sla_scan_complete", extra={"context": {
        "tenant_id": tenant_id, "breaches": len(breaches),
        "notified": notified, "sla_minutes": sla_minutes,
    }})
    return SlaResult(breaches=len(breaches), notified=notified)


# ───────────────────────── Inactivity scanner (R15) ────────────────────
async def scan_inactive_agents(*, tenant_id: str, threshold_minutes: int = 30) -> InactivityResult:
    """R15 — agentes con tickets accionables abiertos y `last_update` >
    threshold quedan marcados con un evento system en el primero de sus
    tickets accionables (para que el supervisor lo vea en la torre).
    """
    db = get_db()
    now = _now()
    cutoff_iso = _iso(now - timedelta(minutes=threshold_minutes))
    pipeline = [
        {"$match": {
            "tenant_id": tenant_id,
            "status": {"$nin": list(TERMINAL_TICKET_STATUSES) + list(WAITING_STATUSES)},
            "assigned_agent_id": {"$ne": None},
        }},
        {"$group": {
            "_id": "$assigned_agent_id",
            "last_update": {"$max": "$updated_at"},
            "open_actionable": {"$sum": 1},
            "first_ticket_id": {"$first": "$id"},
        }},
        {"$match": {"last_update": {"$lt": cutoff_iso}, "open_actionable": {"$gt": 0}}},
    ]
    rows = await db.tickets.aggregate(pipeline).to_list(length=500)
    notified = 0
    for r in rows:
        last = await db.timeline_events.find_one(
            {"tenant_id": tenant_id, "ticket_id": r["first_ticket_id"],
             "event_type": "agent_inactive"},
            {"_id": 0}, sort=[("created_at", -1)],
        )
        if last and last["created_at"] >= cutoff_iso:
            continue
        await db.timeline_events.insert_one({
            "id": _new_id(),
            "tenant_id": tenant_id,
            "ticket_id": r["first_ticket_id"],
            "event_type": "agent_inactive",
            "actor_type": "system",
            "actor_id": None,
            "channel": "internal",
            "payload": {
                "agent_id": r["_id"],
                "last_update": r["last_update"],
                "open_actionable": r["open_actionable"],
                "threshold_minutes": threshold_minutes,
            },
            "created_at": _iso(now),
        })
        notified += 1
    log.info("inactivity_scan_complete", extra={"context": {
        "tenant_id": tenant_id, "inactive_agents": len(rows), "notified": notified,
    }})
    return InactivityResult(inactive_agents=len(rows), notified=notified)


# ───────────────────────── Claims SLA scanner (P1.1 / R28) ─────────────
async def scan_claim_sla(*, tenant_id: str,
                         override_hours: dict | None = None) -> ClaimSlaResult:
    """Detecta reclamos NO terminales con tiempo en su estado actual > umbral.
    Lee `sla_config` del tenant si existe (override por estado), sino usa
    DEFAULT_CLAIM_SLA_HOURS. Registra `claim_sla_breach` en `claim_events`
    con dedupe por estado (no re-notifica si ya hay uno reciente).

    Bundle D · Mayo 2026 (UX-LATAM-006): cuando el tenant tiene
    `sla_config.respect_mx_holidays=True`, el cutoff respeta sáb/dom/feriados
    nacionales mexicanos. Esto evita falsos positivos en reclamos cuyos
    plazos legales (días hábiles) cruzan feriados.
    """
    db = get_db()
    cfg_doc = await db.sla_config.find_one(
        {"tenant_id": tenant_id, "scope": "claims"}, {"_id": 0},
    )
    cfg = dict(DEFAULT_CLAIM_SLA_HOURS)
    if cfg_doc and isinstance(cfg_doc.get("by_estado"), dict):
        cfg.update({k: int(v) for k, v in cfg_doc["by_estado"].items() if isinstance(v, (int, float))})
    if override_hours:
        cfg.update({k: int(v) for k, v in override_hours.items()})
    respect_holidays = bool(cfg_doc and cfg_doc.get("respect_mx_holidays"))

    now = _now()
    claims = await db.claims.find(
        {"tenant_id": tenant_id, "is_terminal": False}, {"_id": 0},
    ).to_list(length=2000)
    breaches = 0
    notified = 0

    # Pre-cargar set de festivos del rango relevante (90 días atrás)
    holiday_set: set[str] = set()
    if respect_holidays:
        from datetime import date as _date
        await db.mx_holidays.create_index([("date", 1)])
        cursor = db.mx_holidays.find(
            {"$or": [{"tenant_id": None}, {"tenant_id": tenant_id}],
             "is_optional": False},
            {"_id": 0, "date": 1},
        )
        async for h in cursor:
            holiday_set.add(h["date"])

    def _is_business(dt: datetime) -> bool:
        if dt.weekday() >= 5:
            return False
        return dt.date().isoformat() not in holiday_set

    def _business_cutoff(start: datetime, hours: int) -> datetime:
        """Resta `hours` desde now retrocediendo solo en días hábiles cuando
        respect_holidays=True. Aproximación: se cuentan horas absolutas pero
        se 'salta' días no hábiles en el calendario."""
        if not respect_holidays:
            return start - timedelta(hours=hours)
        # Estrategia: avanzar hacia atrás día por día hasta acumular `hours`
        # de horas hábiles (24h por día hábil).
        cursor = start
        remaining = hours
        while remaining > 0:
            cursor = cursor - timedelta(hours=1)
            if _is_business(cursor):
                remaining -= 1
        return cursor

    for c in claims:
        max_hours = cfg.get(c["estado"])
        if not max_hours:
            continue
        cutoff = _business_cutoff(now, max_hours)
        last_update = _parse(c.get("updated_at") or c.get("promoted_at") or _iso(now))
        if last_update >= cutoff:
            continue
        breaches += 1
        # Dedupe — skip si ya existe un claim_sla_breach posterior al cutoff
        last = await db.claim_events.find_one(
            {"tenant_id": tenant_id, "claim_id": c["id"],
             "event_type": "claim_sla_breach"},
            {"_id": 0}, sort=[("created_at", -1)],
        )
        if last and last["created_at"] >= _iso(cutoff):
            continue
        await db.claim_events.insert_one({
            "id": _new_id(),
            "tenant_id": tenant_id,
            "claim_id": c["id"],
            "event_type": "claim_sla_breach",
            "actor_type": "system",
            "actor_id": None,
            "estado_anterior": c["estado"],
            "estado_nuevo": c["estado"],
            "payload": {
                "estado": c["estado"],
                "max_hours": max_hours,
                "respect_mx_holidays": respect_holidays,
                "last_update": c.get("updated_at"),
                "age_hours": int((now - last_update).total_seconds() // 3600),
            },
            "created_at": _iso(now),
        })
        notified += 1
    log.info("claim_sla_scan_complete", extra={"context": {
        "tenant_id": tenant_id, "breaches": breaches, "notified": notified,
        "respect_mx_holidays": respect_holidays,
    }})
    return ClaimSlaResult(breaches=breaches, notified=notified)


# ───────────────────────── helpers ─────────────────────────────────────
def _new_id() -> str:
    from core.uuid import new_id
    return new_id()


def _parse(iso: str) -> datetime:
    """Parse ISO with or without 'Z' suffix into a tz-aware datetime."""
    s = (iso or "").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return _now()
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
