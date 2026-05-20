"""Guías repository — enforces R02 (terminal state never overwritten).

This is the canonical implementation of the rule from MYEXCELLENCE.md
sec 5.1 / sec 5.4. Bootstrap test ``test_terminal_state.py`` validates it.
"""
from __future__ import annotations
from datetime import datetime, timezone

from core.errors import TerminalStateException
from core.logger import log

from .base import BaseRepository

TERMINAL_INTERNAL_STATUSES = {"delivered", "returned"}
INCIDENT_STATUSES = {"exception", "cancelled"}


class GuiaRepository(BaseRepository):
    collection_name = "guias"

    async def update_status(
        self,
        guia_id: str,
        *,
        new_carrier_status: str,
        new_internal_status: str | None = None,
    ) -> bool:
        """R02 — silent discard on guías with is_terminal=True.

        Returns True if the row was updated, False if the update was rejected.
        """
        guia = await self.find_one({"id": guia_id})
        if not guia:
            return False

        if guia.get("is_terminal"):
            log.warning(
                "TERMINAL_STATE_PROTECTION",
                extra={"context": {
                    "guia_id": guia_id,
                    "tenant_id": self.tenant_id,
                    "attempted_carrier_status": new_carrier_status,
                    "attempted_internal_status": new_internal_status,
                }},
            )
            return False

        updates = {
            "carrier_status": new_carrier_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if new_internal_status:
            updates["internal_status"] = new_internal_status
            if new_internal_status in TERMINAL_INTERNAL_STATUSES:
                updates["is_terminal"] = True

        modified = await self.update_one({"id": guia_id}, updates)
        if modified and new_internal_status == "delivered":
            # PROMPT 39 — webhook guia.delivered (R48)
            try:
                from services.webhooks.dispatcher import OutboundWebhookDispatcher
                full = await self.find_one({"id": guia_id})
                if full:
                    await OutboundWebhookDispatcher.dispatch(
                        tenant_id=self.tenant_id,
                        client_id=full.get("client_id", ""),
                        event_type="guia.delivered",
                        source_id=guia_id,
                        data={
                            "guia_id": guia_id,
                            "client_id": full.get("client_id"),
                            "carrier_id": full.get("carrier_id"),
                            "tracking_id": full.get("tracking_id"),
                            "delivered_at": full.get("updated_at"),
                        },
                    )
            except Exception:  # noqa: BLE001
                log.exception("webhook_guia_delivered_failed",
                              extra={"context": {"guia_id": guia_id}})
        return modified > 0

    async def force_terminal(self, guia_id: str, internal_status: str) -> bool:
        """Test/seed-only helper to flip a guía to terminal.

        Production code paths must reach terminal state through update_status
        with internal_status ∈ TERMINAL_INTERNAL_STATUSES.
        """
        if internal_status not in TERMINAL_INTERNAL_STATUSES:
            raise ValueError(f"Not a terminal status: {internal_status}")
        return await self.update_one(
            {"id": guia_id},
            {"is_terminal": True, "internal_status": internal_status,
             "updated_at": datetime.now(timezone.utc).isoformat()},
        ) > 0

    async def create_minimal(self, *, tracking_id: str, carrier_id: str,
                             client_id: str, internal_status: str = "in_transit") -> dict:
        return await self.insert({
            "tracking_id": tracking_id,
            "carrier_id": carrier_id,
            "client_id": client_id,
            "subclient_id": None,
            "carrier_status": "created",
            "internal_status": internal_status,
            "is_terminal": False,
            "ingest_source": "manual",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    def raise_if_terminal(self, guia: dict) -> None:
        if guia.get("is_terminal"):
            raise TerminalStateException()
