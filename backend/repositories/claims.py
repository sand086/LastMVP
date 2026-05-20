"""Claims repositories — R28 terminal guard + append-only events (R30)."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from core.db import get_db
from core.logger import log
from core.uuid import new_id
from repositories.append_only import _AppendOnlyRepository
from repositories.base import BaseRepository

from models.claim import TERMINAL_CLAIM_STATUSES


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ClaimRepository(BaseRepository):
    """Tenant-scoped claims store. R29 (UNIQUE active per ticket) is enforced
    via Mongo partial index — see ``ensure_claim_indexes``.
    """
    collection_name = "claims"

    async def create(
        self,
        *,
        ticket_id: str,
        client_id: str,
        tipo_dano: str,
        monto_reclamado: float,
        divisa: str,
        promoted_by: str,
    ) -> dict:
        """Create a fresh ``promovido`` claim. Raises ``DuplicateClaimError`` if
        an active claim already exists for the ticket (R29)."""
        # Pre-flight check; the partial unique index is the real authority.
        existing = await self.find_one({"ticket_id": ticket_id, "is_terminal": False})
        if existing:
            raise DuplicateClaimError(existing["id"])
        from pymongo.errors import DuplicateKeyError
        try:
            return await self.insert({
                "ticket_id": ticket_id,
                "client_id": client_id,
                "estado": "promovido",
                "is_terminal": False,
                "tipo_dano": tipo_dano,
                "monto_reclamado": monto_reclamado,
                "divisa": divisa,
                "promoted_by": promoted_by,
                "promoted_at": _now_iso(),
                "assigned_to": None,
                "carrier_dictamen_at": None,
                "conciliado_at": None,
                "expediente": {},  # filled progressively
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
            })
        except DuplicateKeyError:
            raise DuplicateClaimError(ticket_id)

    async def update_state(self, claim_id: str, new_state: str, *, extra: dict | None = None) -> bool:
        """R28 — claims in a terminal state silently ignore updates."""
        existing = await self.find_one({"id": claim_id})
        if not existing:
            return False
        if existing.get("is_terminal"):
            log.warning("CLAIM_TERMINAL_PROTECTION", extra={"context": {
                "claim_id": claim_id, "tenant_id": self.tenant_id,
                "current_state": existing["estado"], "attempted_target": new_state,
            }})
            return False
        updates = {
            "estado": new_state,
            "updated_at": _now_iso(),
        }
        if new_state in TERMINAL_CLAIM_STATUSES:
            updates["is_terminal"] = True
            updates["conciliado_at"] = _now_iso() if new_state == "conciliado" else None
        if extra:
            updates.update(extra)
        modified = await self.update_one({"id": claim_id}, updates)
        return modified > 0

    async def by_ticket_active(self, ticket_id: str) -> Optional[dict]:
        return await self.find_one({"ticket_id": ticket_id, "is_terminal": False})

    async def patch_expediente(self, claim_id: str, updates: dict) -> bool:
        if not updates:
            return False
        body = {f"expediente.{k}": v for k, v in updates.items()}
        body["updated_at"] = _now_iso()
        modified = await self.col.update_one(
            self._scope({"id": claim_id, "is_terminal": False}),
            {"$set": body},
        )
        return modified.modified_count > 0


class ClaimEventRepository(_AppendOnlyRepository):
    """R30 — append-only. NO update / delete by design (inherited)."""
    collection_name = "claim_events"

    async def record(
        self,
        *,
        claim_id: str,
        event_type: str,
        actor_type: str,  # system | agent | coordinator | carrier
        actor_id: Optional[str] = None,
        estado_anterior: Optional[str] = None,
        estado_nuevo: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> dict:
        return await self.append({
            "claim_id": claim_id,
            "event_type": event_type,
            "estado_anterior": estado_anterior,
            "estado_nuevo": estado_nuevo,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "payload": payload or {},
        })


class IndemnizationRepository(BaseRepository):
    collection_name = "claim_indemnizations"

    async def upsert(self, *, claim_id: str, monto_aprobado: float, divisa: str,
                     carrier_referencia: Optional[str] = None) -> dict:
        now = _now_iso()
        await self.col.update_one(
            self._scope({"claim_id": claim_id}),
            {
                "$set": {"monto_aprobado": monto_aprobado, "divisa": divisa,
                         "carrier_referencia": carrier_referencia, "updated_at": now},
                "$setOnInsert": {"id": new_id(), "tenant_id": self.tenant_id,
                                 "claim_id": claim_id, "created_at": now},
            },
            upsert=True,
        )
        return await self.find_one({"claim_id": claim_id})

    async def conciliate(self, claim_id: str, *, monto: float, divisa: str,
                         conciliado_por: str, notas: Optional[str] = None) -> bool:
        modified = await self.col.update_one(
            self._scope({"claim_id": claim_id}),
            {"$set": {
                "monto_conciliado": monto, "divisa_conciliado": divisa,
                "conciliado_por": conciliado_por, "conciliado_at": _now_iso(),
                "notas_conciliacion": notas,
            }},
        )
        return modified.modified_count > 0


class DuplicateClaimError(Exception):
    """Raised when a ticket already has an active (non-terminal) claim — R29."""
    def __init__(self, claim_id_or_ticket: str):
        super().__init__(f"Active claim already exists ({claim_id_or_ticket})")
        self.claim_id = claim_id_or_ticket


async def ensure_claim_indexes() -> None:
    """Create the partial unique index that enforces R29 in MongoDB."""
    db = get_db()
    # R29 — UNIQUE on (tenant_id, ticket_id) WHERE is_terminal=False
    await db.claims.create_index(
        [("tenant_id", 1), ("ticket_id", 1)],
        unique=True,
        partialFilterExpression={"is_terminal": False},
        name="uq_active_claim_per_ticket",
    )
    await db.claims.create_index([("tenant_id", 1), ("estado", 1)])
    await db.claims.create_index([("tenant_id", 1), ("assigned_to", 1)])
    await db.claim_events.create_index([("tenant_id", 1), ("claim_id", 1), ("created_at", 1)])
    await db.claim_indemnizations.create_index([("tenant_id", 1), ("claim_id", 1)], unique=True)
