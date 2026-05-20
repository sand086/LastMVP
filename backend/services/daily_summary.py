"""Daily Summary — PROMPT 11.5.

Genera el resumen diario por tenant con los KPIs operativos clave y lo envía
por email al supervisor designado del tenant. Cero dependencias externas más
allá del NotificationService ya armado en PROMPT_11.

KPIs incluidos:
  * tickets abiertos / accionables
  * tickets resueltos hoy
  * backlog > 24h sin actualizar
  * automatizaciones ejecutadas hoy (timeline_events.event_type=automation_executed)
  * SLA breaches detectados hoy
  * agentes inactivos detectados hoy
  * reclamos en dictamen carrier > 24h
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from core.db import get_db
from core.logger import log
from repositories.tickets import TERMINAL_TICKET_STATUSES
from services.notification_service import send_email


@dataclass
class DailySummary:
    tenant_id: str
    sent: bool
    to: Optional[str]
    reason: Optional[str]
    metrics: dict


def _today_start() -> str:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _backlog_cutoff() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()


async def compute_metrics(tenant_id: str) -> dict:
    db = get_db()
    today = _today_start()
    backlog_cut = _backlog_cutoff()
    open_tickets = await db.tickets.count_documents({
        "tenant_id": tenant_id,
        "status": {"$nin": list(TERMINAL_TICKET_STATUSES)},
    })
    resolved_today = await db.tickets.count_documents({
        "tenant_id": tenant_id,
        "status": {"$in": list(TERMINAL_TICKET_STATUSES)},
        "updated_at": {"$gte": today},
    })
    backlog_aged = await db.tickets.count_documents({
        "tenant_id": tenant_id,
        "status": {"$nin": list(TERMINAL_TICKET_STATUSES)},
        "updated_at": {"$lt": backlog_cut},
    })
    automations_today = await db.timeline_events.count_documents({
        "tenant_id": tenant_id, "event_type": "automation_executed",
        "created_at": {"$gte": today},
    })
    sla_breaches_today = await db.timeline_events.count_documents({
        "tenant_id": tenant_id, "event_type": "sla_breach",
        "created_at": {"$gte": today},
    })
    inactive_today = await db.timeline_events.count_documents({
        "tenant_id": tenant_id, "event_type": "agent_inactive",
        "created_at": {"$gte": today},
    })
    claims_in_dictamen = await db.claims.count_documents({
        "tenant_id": tenant_id, "estado": "en_dictamen_carrier",
        "updated_at": {"$lt": backlog_cut},
    })
    return {
        "open_tickets": open_tickets,
        "resolved_today": resolved_today,
        "backlog_aged_24h": backlog_aged,
        "automations_today": automations_today,
        "sla_breaches_today": sla_breaches_today,
        "agents_inactive_today": inactive_today,
        "claims_dictamen_aging": claims_in_dictamen,
        "ai": await _ai_section_metrics(tenant_id),
    }


async def _ai_section_metrics(tenant_id: str) -> dict:
    """Métricas del módulo IA para el resumen diario (P1 · PROMPT 26)."""
    db = get_db()
    today = _today_start()
    # Invocaciones de hoy
    pipeline = [
        {"$match": {"tenant_id": tenant_id, "created_at": {"$gte": today}}},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
            "cost_usd": {"$sum": {"$ifNull": ["$cost_usd", 0]}},
            "tokens_in": {"$sum": {"$ifNull": ["$input_tokens", 0]}},
            "tokens_out": {"$sum": {"$ifNull": ["$output_tokens", 0]}},
        }},
    ]
    by_status = {row["_id"]: row async for row in db.ai_invocation_log.aggregate(pipeline)}
    invocations = sum(r["count"] for r in by_status.values())
    cost_usd = round(sum(r["cost_usd"] for r in by_status.values()), 6)
    cache_hits = by_status.get("cache_hit", {}).get("count", 0)
    capped = by_status.get("capped", {}).get("count", 0)
    errors = by_status.get("error", {}).get("count", 0) + by_status.get("provider_unavailable", {}).get("count", 0)
    cache_hit_rate = (cache_hits / invocations * 100) if invocations else 0
    # Top 3 features
    top = []
    async for r in db.ai_invocation_log.aggregate([
        {"$match": {"tenant_id": tenant_id, "created_at": {"$gte": today},
                    "status": {"$in": ["success", "cache_hit"]}}},
        {"$group": {"_id": "$feature_code", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}, {"$limit": 3},
    ]):
        top.append({"feature": r["_id"], "count": r["count"]})
    return {
        "invocations_today": invocations,
        "cost_usd_today": cost_usd,
        "cache_hits_today": cache_hits,
        "cache_hit_rate_pct": round(cache_hit_rate, 1),
        "capped_today": capped,
        "errors_today": errors,
        "top_features_today": top,
    }


def render_summary_email(*, tenant_name: str, metrics: dict) -> tuple[str, str]:
    cells = [
        ("Tickets abiertos",          metrics["open_tickets"]),
        ("Resueltos hoy",             metrics["resolved_today"]),
        ("Backlog > 24h",             metrics["backlog_aged_24h"]),
        ("Automatizaciones ejecutadas hoy", metrics["automations_today"]),
        ("SLA breaches hoy",          metrics["sla_breaches_today"]),
        ("Agentes inactivos hoy",     metrics["agents_inactive_today"]),
        ("Reclamos en dictamen >24h", metrics["claims_dictamen_aging"]),
    ]
    ai = metrics.get("ai") or {}
    ai_cells = []
    if ai.get("invocations_today"):
        ai_cells = [
            ("Invocaciones IA",            ai["invocations_today"]),
            ("Costo IA (USD)",             f"${ai['cost_usd_today']:.4f}"),
            ("Cache hit rate",             f"{ai['cache_hit_rate_pct']}%"),
            ("Bloqueos por tope",          ai["capped_today"]),
            ("Errores de proveedor",       ai["errors_today"]),
        ]
    rows_html = "".join(
        f'<tr><td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;">{label}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;text-align:right;'
        f'font-family:\'IBM Plex Mono\',monospace;font-weight:600;">{value}</td></tr>'
        for label, value in cells
    )
    ai_rows_html = "".join(
        f'<tr><td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;">{label}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;text-align:right;'
        f'font-family:\'IBM Plex Mono\',monospace;font-weight:600;">{value}</td></tr>'
        for label, value in ai_cells
    )
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ai_block_html = ""
    if ai_cells:
        ai_block_html = (
            f'<h3 style="color:#1F3A5F;margin-top:24px;margin-bottom:6px;font-size:14px;">'
            f'IA · módulo de configuración</h3>'
            f'<table style="border-collapse:collapse;width:100%;margin:8px 0 16px 0;'
            f'border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">'
            f'<tbody>{ai_rows_html}</tbody></table>'
        )
    html = (
        f'<div style="font-family:\'IBM Plex Sans\',-apple-system,sans-serif;'
        f'max-width:560px;margin:0 auto;color:#1F3A5F;line-height:1.5;">'
        f'<h2 style="color:#C2410C;margin-bottom:6px;">Resumen diario · {tenant_name}</h2>'
        f'<p style="color:#6b7280;margin-top:0;font-size:12px;">'
        f'Operación al cierre del {today} (UTC).</p>'
        f'<table style="border-collapse:collapse;width:100%;margin:16px 0;'
        f'border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">'
        f'<tbody>{rows_html}</tbody></table>'
        f'{ai_block_html}'
        f'<p style="font-size:11px;color:#9ca3af;">'
        f'Generado automáticamente por MyExcellence v2.1. Para cambiar el destinatario '
        f'edita el supervisor del tenant en /admin/jerarquia.</p></div>'
    )
    text_lines = [f"Resumen diario · {tenant_name} ({today} UTC)", "", "—" * 40]
    for label, value in cells:
        text_lines.append(f"{label.ljust(36)} {value}")
    if ai_cells:
        text_lines += ["", "IA · módulo de configuración"]
        for label, value in ai_cells:
            text_lines.append(f"{label.ljust(36)} {value}")
    text_lines += ["", "— MyExcellence"]
    return html, "\n".join(text_lines)


async def send_for_tenant(tenant_id: str) -> DailySummary:
    db = get_db()
    tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0})
    if not tenant:
        return DailySummary(tenant_id, False, None, "tenant_not_found", {})
    # Pick the first supervisor as recipient. Fallback to first admin.
    recipient = await db.users.find_one(
        {"tenant_id": tenant_id, "role": "supervisor", "status": "active"},
        {"_id": 0, "password_hash": 0},
    )
    if not recipient:
        recipient = await db.users.find_one(
            {"tenant_id": tenant_id, "role": "admin", "status": "active"},
            {"_id": 0, "password_hash": 0},
        )
    if not recipient or not recipient.get("email"):
        return DailySummary(tenant_id, False, None, "no_recipient", {})

    metrics = await compute_metrics(tenant_id)
    html, text = render_summary_email(tenant_name=tenant.get("name") or "—", metrics=metrics)
    result = await send_email(
        to=recipient["email"],
        subject=f"[MyExcellence] Resumen diario · {tenant.get('name')}",
        html=html, text=text,
        tags={"kind": "daily_summary", "tenant_id": tenant_id[:8]},
    )
    log.info("daily_summary_sent", extra={"context": {
        "tenant_id": tenant_id, "to": recipient["email"],
        "ok": result.ok, "mock": result.mock, "metrics": metrics,
    }})
    return DailySummary(
        tenant_id=tenant_id, sent=result.ok, to=recipient["email"],
        reason=result.reason, metrics=metrics,
    )


async def send_for_all_tenants() -> list[dict]:
    db = get_db()
    tenants = await db.tenants.find({"status": "active"}, {"_id": 0}).to_list(length=500)
    out: list[dict] = []
    for t in tenants:
        s = await send_for_tenant(t["id"])
        out.append({"tenant_id": s.tenant_id, "to": s.to, "sent": s.sent,
                    "reason": s.reason, "metrics": s.metrics})
    return out
