"""CAE Status Normalizer — REAL implementation (PROMPT 06).

Looks up ``carrier_status_catalog`` for a (carrier_id, raw_code, api_version)
tuple. If found returns a fully-typed ``NormalizedStatus``. If missing we fall
back to ``unknown`` and log the code into ``cae_unmapped_codes`` (R25) with
upsert semantics so admins can later promote it to the catalog.

Catalog rows can be tenant-specific OR global (``tenant_id=None``). Tenant
rows take precedence.
"""
from __future__ import annotations
from datetime import datetime, timezone

from core.db import get_db
from core.logger import log
from core.uuid import new_id

from .interface import NormalizedStatus, RawCarrierEvent

_CANONICAL_VALUES = {
    "in_transit", "delivered", "returned",
    "exception", "cancelled", "unknown",
}

_TERMINAL_CANONICAL = {"delivered", "returned"}


class StatusNormalizer:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    async def normalize(self, event: RawCarrierEvent) -> NormalizedStatus:
        db = get_db()
        # Tenant-specific row wins; otherwise global (tenant_id null)
        row = await db.carrier_status_catalog.find_one(
            {
                "carrier_id": event.carrier_id,
                "raw_code": event.raw_code,
                "api_version": event.api_version,
                "active": True,
                "$or": [{"tenant_id": self.tenant_id}, {"tenant_id": None}],
            },
            {"_id": 0},
            sort=[("tenant_id", -1)],  # nulls sort last → tenant-specific first
        )
        if row:
            canonical = row.get("canonical_status", "unknown")
            return NormalizedStatus(
                canonical_status=canonical,
                incident_type=row.get("incident_type"),
                is_terminal=bool(row.get("is_terminal")) or canonical in _TERMINAL_CANONICAL,
                requires_action=bool(row.get("requires_action")),
                display_label_es=row.get("display_label_es", canonical),
                confidence=int(row.get("confidence", 100)),
                raw_event=event,
            )

        await self._record_unmapped(event)
        log.warning("CAE_UNMAPPED", extra={"context": {
            "carrier_id": event.carrier_id, "raw_code": event.raw_code,
            "api_version": event.api_version, "tenant_id": self.tenant_id,
        }})
        return NormalizedStatus(
            canonical_status="unknown",
            incident_type=None,
            is_terminal=False,
            requires_action=False,
            display_label_es=event.raw_description or event.raw_code,
            confidence=0,
            raw_event=event,
        )

    async def _record_unmapped(self, event: RawCarrierEvent) -> None:
        col = get_db()["cae_unmapped_codes"]
        now = datetime.now(timezone.utc).isoformat()
        await col.update_one(
            {
                "carrier_id": event.carrier_id,
                "raw_code": event.raw_code,
                "api_version": event.api_version,
            },
            {
                "$setOnInsert": {
                    "id": new_id(),
                    "raw_description": event.raw_description,
                    "first_seen": now,
                },
                "$set": {"last_seen": now},
                "$inc": {"occurrences": 1},
            },
            upsert=True,
        )
