"""Tickets repository + automatic timeline emission (R04, sec 5.4)."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from core.uuid import new_id

from .append_only import TimelineRepository
from .base import BaseRepository

TERMINAL_TICKET_STATUSES = {"resolved", "closed"}


async def _emit_webhook_safely(coro_func, **kwargs) -> None:
    """Llamada al dispatcher con manejo defensivo — un fallo en webhooks NUNCA
    debe bloquear la escritura del ticket."""
    try:
        await coro_func(**kwargs)
    except Exception:  # noqa: BLE001
        from core.logger import log
        log.exception("webhook_emit_failed", extra={"context": kwargs})


class TicketRepository(BaseRepository):
    collection_name = "tickets"

    def __init__(self, tenant_id: str):
        super().__init__(tenant_id=tenant_id)
        self.timeline = TimelineRepository(tenant_id=tenant_id)

    async def create_from_workflow(
        self,
        *,
        client_id: str,
        subclient_id: Optional[str],
        guia_id: str,
        motivo_id: Optional[str],
        carrier_id: Optional[str],
        carrier_status_raw: str,
        incident_type: Optional[str],
        canonical_status: Optional[str],
        source: str = "ingest",
        incident_subtype: Optional[str] = None,
        carrier_incident_detail: Optional[dict] = None,
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": new_id(),
            "tenant_id": self.tenant_id,
            "client_id": client_id,
            "subclient_id": subclient_id,
            "guia_id": guia_id,
            "carrier_id": carrier_id,
            "motivo_id": motivo_id,
            "solucion_id": None,
            "status": "pending",
            "assigned_agent_id": None,
            "incident_type": incident_type,
            "incident_subtype": incident_subtype,
            "carrier_incident_detail": carrier_incident_detail or None,
            "canonical_status": canonical_status,
            "carrier_status_raw": carrier_status_raw,
            "source": source,
            "created_at": now,
            "updated_at": now,
        }
        await self.col.insert_one(doc)
        doc.pop("_id", None)
        await self.timeline.record(
            ticket_id=doc["id"],
            event_type="created",
            actor_type="system",
            channel="internal",
            payload={
                "source": source,
                "incident_type": incident_type,
                "canonical_status": canonical_status,
                "carrier_status_raw": carrier_status_raw,
            },
        )
        # PROMPT 39 — Webhook saliente ticket.created (R48)
        from services.webhooks.dispatcher import OutboundWebhookDispatcher
        await _emit_webhook_safely(
            OutboundWebhookDispatcher.dispatch,
            tenant_id=self.tenant_id, client_id=client_id,
            event_type="ticket.created", source_id=doc["id"],
            data={"ticket": {
                "id": doc["id"], "client_id": client_id,
                "carrier_id": carrier_id, "guia_id": guia_id,
                "tracking_id": None, "status": "pending",
                "motivo_id": motivo_id, "incident_type": incident_type,
                "destinatario": {},
                "created_at": doc["created_at"],
            }},
        )
        return doc

    async def open_for_guia(self, guia_id: str) -> Optional[dict]:
        return await self.find_one({
            "guia_id": guia_id,
            "status": {"$in": ["pending", "in_progress", "waiting_client", "waiting_carrier", "claim"]},
        })

    async def assign(self, ticket_id: str, agent_id: str, *, actor_id: str | None = None) -> bool:
        modified = await self.update_one({"id": ticket_id}, {
            "assigned_agent_id": agent_id,
            "status": "in_progress",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        if modified:
            await self.timeline.record(
                ticket_id=ticket_id,
                event_type="assigned",
                actor_type="system" if not actor_id else "user",
                actor_id=actor_id,
                channel="internal",
                payload={"agent_id": agent_id},
            )
        return modified > 0

    async def change_status(self, ticket_id: str, new_status: str, *,
                            actor_id: str | None = None, reason: str | None = None) -> bool:
        # Resolve previous status before update for webhook payload
        prev = await self.find_one({"id": ticket_id})
        previous_status = prev.get("status") if prev else None
        client_id = prev.get("client_id") if prev else None

        modified = await self.update_one({"id": ticket_id}, {
            "status": new_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        if modified:
            await self.timeline.record(
                ticket_id=ticket_id,
                event_type="status_change",
                actor_type="system" if not actor_id else "user",
                actor_id=actor_id,
                channel="internal",
                payload={"new_status": new_status, "reason": reason},
            )
            # PROMPT 39 — webhook ticket.status_changed (siempre)
            from services.webhooks.dispatcher import OutboundWebhookDispatcher
            if client_id:
                await _emit_webhook_safely(
                    OutboundWebhookDispatcher.dispatch,
                    tenant_id=self.tenant_id, client_id=client_id,
                    event_type="ticket.status_changed", source_id=ticket_id,
                    data={
                        "ticket_id": ticket_id,
                        "previous_status": previous_status,
                        "new_status": new_status,
                        "actor_id": actor_id, "reason": reason,
                    },
                )
                # Si llegó a terminal → emit ticket.closed
                if new_status in TERMINAL_TICKET_STATUSES:
                    await _emit_webhook_safely(
                        OutboundWebhookDispatcher.dispatch,
                        tenant_id=self.tenant_id, client_id=client_id,
                        event_type="ticket.closed", source_id=ticket_id,
                        data={
                            "ticket_id": ticket_id,
                            "final_status": new_status,
                            "closed_by": actor_id,
                        },
                    )
        return modified > 0

    async def set_solucion(self, ticket_id: str, *, solucion_id: str, channel: str,
                           actor_id: str | None = None) -> bool:
        modified = await self.update_one({"id": ticket_id}, {
            "solucion_id": solucion_id,
            "selected_channel": channel,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        if modified:
            await self.timeline.record(
                ticket_id=ticket_id,
                event_type="solucion_set",
                actor_type="user" if actor_id else "system",
                actor_id=actor_id,
                channel="internal",
                payload={"solucion_id": solucion_id, "channel": channel},
            )
        return modified > 0


async def first_available_agent(tenant_id: str) -> Optional[dict]:
    """Pick the first active user with role=agent in the tenant."""
    from core.db import get_db
    return await get_db().users.find_one(
        {"tenant_id": tenant_id, "role": "agent", "status": "active"},
        {"_id": 0, "password_hash": 0},
        sort=[("last_login_at", -1), ("created_at", 1)],
    )
