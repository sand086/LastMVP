"""Iter54 — P1.3 — Cron de escalation por falta de respuesta del cliente.

Documento del cliente: tras notificar 3 veces al responsable sin respuesta,
al 4to correo se debe notificar **retorno a origen** y cerrar el ticket.

Servicio puro (sin scheduler). El scheduler lo invoca cada 60min.

Lógica:
  1. Buscar tickets con `client_notifications_count >= 3` Y status no terminal
     Y `last_client_notification_at < ahora - GRACE_HOURS` (default 48h).
  2. Para cada uno:
     a. Emitir email `final_return_to_origin` al ops_contact_email del cliente
        (vía EmailDispatcher/Resend).
     b. Cambiar status a `resolved` con reason="retorno a origen — sin respuesta".
     c. Registrar timeline_event `auto_escalated`.

Idempotente: una vez resolved, no vuelve a entrar al scan.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from core.db import get_db
from core.logger import log
from repositories.tickets import TERMINAL_TICKET_STATUSES, TicketRepository


@dataclass
class EscalationResult:
    scanned: int
    escalated: int
    skipped: int


DEFAULT_MAX_NOTIFICATIONS = 3
DEFAULT_GRACE_HOURS = 48


async def scan_unresponsive_tickets(
    *, tenant_id: str,
    max_notifications: int = DEFAULT_MAX_NOTIFICATIONS,
    grace_hours: int = DEFAULT_GRACE_HOURS,
    dry_run: bool = False,
) -> EscalationResult:
    """Detecta y escala tickets sin respuesta del cliente."""
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=grace_hours)).isoformat()
    query = {
        "tenant_id": tenant_id,
        "status": {"$nin": list(TERMINAL_TICKET_STATUSES)},
        "client_notifications_count": {"$gte": max_notifications},
        "last_client_notification_at": {"$lt": cutoff},
    }
    candidates = await db.tickets.find(query, {"_id": 0}).to_list(length=500)
    scanned = len(candidates)
    escalated = 0
    skipped = 0
    if not candidates:
        return EscalationResult(scanned=0, escalated=0, skipped=0)

    repo = TicketRepository(tenant_id=tenant_id)
    for t in candidates:
        try:
            if dry_run:
                escalated += 1
                continue
            await _send_final_warning_and_close(
                tenant_id=tenant_id, ticket=t, repo=repo)
            escalated += 1
        except Exception:  # noqa: BLE001
            log.exception("escalation_ticket_failed",
                          extra={"context": {"ticket_id": t.get("id")}})
            skipped += 1
    log.info("escalation_scan_complete", extra={"context": {
        "tenant_id": tenant_id, "scanned": scanned,
        "escalated": escalated, "skipped": skipped,
    }})
    return EscalationResult(scanned=scanned, escalated=escalated, skipped=skipped)


async def _send_final_warning_and_close(*, tenant_id: str, ticket: dict,
                                        repo: TicketRepository) -> None:
    """Emite el email final + cierra el ticket + registra timeline."""
    db = get_db()
    client = await db.clients.find_one(
        {"id": ticket.get("client_id"), "tenant_id": tenant_id},
        {"_id": 0, "ops_contact_email": 1, "ops_contact_name": 1, "name": 1},
    ) or {}
    guia = await db.guias.find_one(
        {"id": ticket.get("guia_id"), "tenant_id": tenant_id},
        {"_id": 0, "tracking_id": 1, "carrier_code": 1, "carrier_incidence": 1},
    ) or {}

    to_email = client.get("ops_contact_email")
    if to_email:
        from services.email_templates import render_for_tenant
        ctx = {
            "recipient_name": client.get("ops_contact_name") or client.get("name") or "Equipo",
            "ticket_id": ticket["id"],
            "tracking_id": guia.get("tracking_id") or "—",
            "carrier_name": guia.get("carrier_code") or "—",
            "incidence_label": guia.get("carrier_incidence") or "",
            "message": "Se realizaron los intentos de notificación pactados sin éxito. "
                       "El paquete será retornado a origen.",
            "cta_url": "", "cta_label": "Ver detalle",
            "tenant_name": "MyExcellence",
        }
        rendered = await render_for_tenant(
            tenant_id=tenant_id, key="final_return_to_origin", ctx=ctx)
        if rendered:
            from services.notification_service import send_email
            await send_email(
                to=to_email,
                subject=rendered["subject"] or f"[MyExcellence] Retorno a origen {ctx['tracking_id']}",
                html=rendered["html"], text=rendered["text"],
                tags={"ticket_id": ticket["id"][:8], "tenant_id": tenant_id[:8],
                      "kind": "final_return"},
            )

    # Cierre del ticket
    await repo.change_status(
        ticket["id"], "resolved",
        reason="retorno a origen — sin respuesta tras 3 notificaciones",
    )

    # Timeline event explícito para auditoría
    await repo.timeline.record(
        ticket_id=ticket["id"],
        event_type="auto_escalated",
        actor_type="system", actor_id=None, channel="email",
        payload={
            "notifications_count": ticket.get("client_notifications_count", 0),
            "action": "return_to_origin",
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    )


# ───────────── Helper para incrementar el contador desde el email path ─────
async def bump_client_notification_counter(
    *, tenant_id: str, ticket_id: str,
) -> int:
    """Incrementa `client_notifications_count` y setea `last_client_notification_at`.

    Llamado desde `AutomationService._execute_email` y desde el endpoint de
    comentarios externos del agente cuando el destinatario es `ops_contact_email`
    del cliente.

    Devuelve el contador resultante.
    """
    from pymongo import ReturnDocument
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    r = await db.tickets.find_one_and_update(
        {"id": ticket_id, "tenant_id": tenant_id},
        {"$inc": {"client_notifications_count": 1},
         "$set": {"last_client_notification_at": now}},
        projection={"_id": 0, "client_notifications_count": 1},
        return_document=ReturnDocument.AFTER,
    )
    return (r or {}).get("client_notifications_count", 0)
