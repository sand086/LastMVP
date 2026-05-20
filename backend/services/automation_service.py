"""AutomationService — PROMPT 11 (R03 + R14).

Ejecuta una solución sobre un ticket SI Y SOLO SI ``automation_check.can_automate``
devuelve ``True``. Esta es la única clase que dispara efectos visibles al
mundo exterior (email, deeplink, futuras llamadas a carrier).

Flujo:
  1. Carga ticket + solucion + cliente.
  2. Pregunta a ``can_automate`` (R03 single source of truth).
  3. Si OK → ejecuta el canal solicitado:
       - email     → Resend con template incident_notice
       - whatsapp  → genera deeplink y lo registra en el timeline
       - api       → reservado para PROMPT 20 (HTTP a carrier)
  4. Registra el resultado en ``timeline_events`` (event_type=automation_executed)
     con payload neutro (sin secretos).
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

from core.db import get_db
from core.errors import MyEException, ErrorCode
from core.logger import log
from core.whatsapp import build_wa_deeplink
from repositories.tickets import TicketRepository
from services.automation_check import can_automate
from services.notification_service import render_incident_notice, send_email


Channel = Literal["email", "whatsapp", "api"]


@dataclass
class AutomationOutcome:
    executed: bool
    channel: Channel
    reason: str
    artifact: Optional[dict] = None  # email_id, deeplink_url, etc.

    def to_dict(self) -> dict:
        return {
            "executed": self.executed, "channel": self.channel,
            "reason": self.reason, "artifact": self.artifact or {},
        }


class AutomationService:
    def __init__(self, tenant_id: str, *, actor_id: Optional[str] = None):
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.tickets = TicketRepository(tenant_id=tenant_id)

    async def execute_for_ticket(self, ticket_id: str, channel: Channel) -> AutomationOutcome:
        ticket = await self.tickets.find_one({"id": ticket_id})
        if not ticket:
            raise MyEException(ErrorCode.RESOURCE_NOT_FOUND, "Ticket no encontrado.")
        if not ticket.get("solucion_id"):
            return AutomationOutcome(False, channel, "no_solucion")

        decision = await can_automate(
            tenant_id=self.tenant_id, client_id=ticket["client_id"],
            solucion_id=ticket["solucion_id"], channel=channel,
        )
        if not decision.can_automate:
            log.info("automation_blocked", extra={"context": {
                "tenant_id": self.tenant_id, "ticket_id": ticket_id,
                "channel": channel, "reason": decision.reason,
            }})
            return AutomationOutcome(False, channel, decision.reason)

        # ────────────── execute ──────────────
        db = get_db()
        client = await db.clients.find_one(
            {"id": ticket["client_id"], "tenant_id": self.tenant_id}, {"_id": 0}
        )
        sol = await db.soluciones.find_one(
            {"id": ticket["solucion_id"], "tenant_id": self.tenant_id}, {"_id": 0}
        )
        guia = await db.guias.find_one(
            {"id": ticket["guia_id"], "tenant_id": self.tenant_id}, {"_id": 0}
        ) if ticket.get("guia_id") else {}

        message = sol.get("template_msg") or sol.get("nombre") or "Notificación MyExcellence"
        recipient_name = (client or {}).get("ops_contact_name") or "Equipo"
        tracking_id = (guia or {}).get("tracking_id") or "—"

        if channel == "email":
            outcome = await self._execute_email(
                ticket_id=ticket_id, client=client or {}, message=message,
                recipient_name=recipient_name, tracking_id=tracking_id,
            )
        elif channel == "whatsapp":
            outcome = await self._execute_whatsapp(
                ticket_id=ticket_id, client=client or {}, message=message,
                tracking_id=tracking_id,
            )
        elif channel == "api":
            return AutomationOutcome(False, channel, "api_channel_not_implemented",
                                     artifact={"note": "PROMPT_20"})
        else:  # pragma: no cover — Pydantic Literal already enforces
            return AutomationOutcome(False, channel, "unknown_channel")

        await self.tickets.timeline.record(
            ticket_id=ticket_id, event_type="automation_executed",
            actor_type="system", actor_id=self.actor_id, channel=channel,
            payload={
                "solucion_id": ticket["solucion_id"], "channel": channel,
                "ok": outcome.executed, "reason": outcome.reason,
                "artifact_keys": list((outcome.artifact or {}).keys()),
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        )
        return outcome

    async def _execute_email(self, *, ticket_id, client, message, recipient_name,
                             tracking_id) -> AutomationOutcome:
        to_email = client.get("ops_contact_email")
        if not to_email:
            return AutomationOutcome(False, "email", "missing_ops_contact_email")
        html, text = render_incident_notice(
            recipient_name=recipient_name, ticket_id=ticket_id,
            tracking_id=tracking_id, message=message,
        )
        result = await send_email(
            to=to_email,
            subject=f"[MyExcellence] Incidencia {tracking_id}",
            html=html, text=text,
            tags={"ticket_id": ticket_id[:8], "tenant_id": self.tenant_id[:8]},
        )
        if not result.ok:
            return AutomationOutcome(False, "email", f"resend_error:{result.reason}")
        # Iter54 — incrementar contador de notificaciones al cliente
        from services.escalation import bump_client_notification_counter
        await bump_client_notification_counter(
            tenant_id=self.tenant_id, ticket_id=ticket_id)
        return AutomationOutcome(True, "email", "ok",
                                 artifact={"email_id": result.id, "to": to_email,
                                           "mock": result.mock})

    async def _execute_whatsapp(self, *, ticket_id, client, message,
                                tracking_id) -> AutomationOutcome:
        wa_phone = client.get("ops_contact_wa")
        if not wa_phone:
            return AutomationOutcome(False, "whatsapp", "missing_ops_contact_wa")
        try:
            url = build_wa_deeplink(wa_phone, f"{message}\n\nTracking: {tracking_id}\nTicket: {ticket_id[:8]}")
        except ValueError as e:
            return AutomationOutcome(False, "whatsapp", f"invalid_phone:{e}")
        return AutomationOutcome(True, "whatsapp", "ok",
                                 artifact={"deeplink": url, "phone": wa_phone})
