"""Repositories para webhooks salientes (PROMPT 39 V3).

Tablas:
  webhook_event_catalog        — catálogo de eventos emitibles (algunos globales)
  webhook_subscriptions        — suscripciones por cliente cartera
  webhook_delivery_log         — append-only (R47)
  webhook_dead_letter_queue    — eventos que agotaron 7 reintentos
  webhook_pending_queue        — cola interna (Mongo en lugar de Redis Streams)
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from core.db import get_db
from core.uuid import new_id

from .append_only import _AppendOnlyRepository
from .base import BaseRepository


class WebhookEventCatalogRepository(BaseRepository):
    collection_name = "webhook_event_catalog"

    def __init__(self, tenant_id: Optional[str] = None):
        super().__init__(tenant_id=tenant_id or "GLOBAL")

    async def list_active(self) -> list[dict]:
        """Devuelve eventos globales (tenant_id=None) o del tenant actual."""
        q = {"active": True}
        if self.tenant_id != "GLOBAL":
            q = {"$and": [{"active": True}, {"$or": [
                {"tenant_id": None}, {"tenant_id": self.tenant_id},
            ]}]}
        cursor = self.col.find(q, {"_id": 0}).sort("event_code", 1).limit(200)
        return await cursor.to_list(length=200)

    async def by_code(self, event_code: str, *, schema_version: str = "v1") -> Optional[dict]:
        return await self.col.find_one(
            {"event_code": event_code, "schema_version": schema_version,
             "active": True},
            {"_id": 0},
        )

    async def upsert_global(self, doc: dict) -> dict:
        body = dict(doc)
        body.setdefault("id", new_id())
        body.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        body["updated_at"] = datetime.now(timezone.utc).isoformat()
        body["tenant_id"] = None  # global
        await self.col.update_one(
            {"event_code": body["event_code"], "schema_version": body.get("schema_version", "v1")},
            {"$set": body},
            upsert=True,
        )
        body.pop("_id", None)
        return body


async def ensure_webhook_indexes() -> None:
    """Indexes para colecciones de webhooks salientes."""
    db = get_db()
    # Catalog: único por (event_code, schema_version, tenant_id|null)
    await db.webhook_event_catalog.create_index(
        [("event_code", 1), ("schema_version", 1), ("tenant_id", 1)],
        unique=True, name="event_code_schema_tenant_idx",
    )
    # Subscriptions
    await db.webhook_subscriptions.create_index(
        [("tenant_id", 1), ("client_id", 1), ("is_active", 1)],
        name="subs_tenant_client_active_idx",
    )
    await db.webhook_subscriptions.create_index(
        [("tenant_id", 1), ("event_codes", 1), ("is_active", 1)],
        name="subs_tenant_event_active_idx",
    )
    # Delivery log: append-only, indexes para queries
    await db.webhook_delivery_log.create_index(
        [("tenant_id", 1), ("subscription_id", 1), ("created_at", -1)],
        name="delivery_subs_created_idx",
    )
    await db.webhook_delivery_log.create_index(
        [("tenant_id", 1), ("event_code", 1), ("source_id", 1), ("created_at", -1)],
        name="delivery_event_source_idx",
    )
    # Pending queue: por next_run_at
    await db.webhook_pending_queue.create_index(
        [("next_run_at", 1), ("claimed_at", 1)],
        name="pending_due_idx",
    )
    # DLQ
    await db.webhook_dead_letter_queue.create_index(
        [("tenant_id", 1), ("resolved", 1), ("moved_to_dlq_at", -1)],
        name="dlq_tenant_resolved_idx",
    )


class WebhookSubscriptionRepository(BaseRepository):
    collection_name = "webhook_subscriptions"

    async def list_for_tenant(self) -> list[dict]:
        cursor = self.col.find(
            {"tenant_id": self.tenant_id},
            {"_id": 0, "hmac_secret_encrypted": 0,
             "hmac_secret_v2_encrypted": 0},
        ).sort("created_at", -1).limit(500)
        items = await cursor.to_list(length=500)
        # Marcar presencia de secret v2 sin exponerlo
        for it in items:
            it["hmac_v2_active"] = bool(it.get("hmac_v2_until"))
        return items

    async def get(self, subscription_id: str) -> Optional[dict]:
        return await self.col.find_one(
            {"id": subscription_id, "tenant_id": self.tenant_id},
            {"_id": 0},
        )

    async def get_decrypted(self, subscription_id: str) -> Optional[dict]:
        """Versión interna — incluye secrets cifrados (para el dispatcher)."""
        return await self.col.find_one(
            {"id": subscription_id, "tenant_id": self.tenant_id},
            {"_id": 0},
        )

    async def find_subscribers_for_event(
        self, *, client_id: str, event_code: str,
    ) -> list[dict]:
        """Suscripciones activas del cliente cartera que escuchan event_code."""
        cursor = self.col.find({
            "tenant_id": self.tenant_id,
            "client_id": client_id,
            "is_active": True,
            "event_codes": event_code,
        }, {"_id": 0})
        return await cursor.to_list(length=100)

    async def create(self, doc: dict) -> dict:
        body = dict(doc)
        body.setdefault("id", new_id())
        body["tenant_id"] = self.tenant_id
        now = datetime.now(timezone.utc).isoformat()
        body.setdefault("created_at", now)
        body["updated_at"] = now
        body.setdefault("is_active", True)
        body.setdefault("is_circuit_open", False)
        body.setdefault("health_score", 100)
        await self.col.insert_one(body)
        body.pop("_id", None)
        return body

    async def patch(self, subscription_id: str, updates: dict) -> int:
        if not updates:
            return 0
        updates = dict(updates)
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        r = await self.col.update_one(
            {"id": subscription_id, "tenant_id": self.tenant_id},
            {"$set": updates},
        )
        return r.modified_count


class WebhookDeliveryLogRepository(_AppendOnlyRepository):
    """R47 — append-only. Sólo expone append() + query()."""
    collection_name = "webhook_delivery_log"

    async def query(self, q: dict, *, limit: int = 200) -> list[dict]:
        full = dict(q)
        full["tenant_id"] = self.tenant_id
        cursor = self.col.find(full, {"_id": 0}).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def in_flight_event(
        self, *, event_type: str, source_id: str, within_seconds: int = 60,
    ) -> Optional[str]:
        """Para R46 idempotencia: ¿hay un event_id reciente para (type, source)?"""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=within_seconds)).isoformat()
        doc = await self.col.find_one({
            "tenant_id": self.tenant_id,
            "event_code": event_type,
            "source_id": source_id,
            "created_at": {"$gte": cutoff},
        }, {"_id": 0, "event_id": 1}, sort=[("created_at", -1)])
        return doc.get("event_id") if doc else None


class WebhookDeadLetterQueueRepository(BaseRepository):
    collection_name = "webhook_dead_letter_queue"

    async def enqueue(self, doc: dict) -> dict:
        body = dict(doc)
        body.setdefault("id", new_id())
        body["tenant_id"] = self.tenant_id
        body.setdefault("moved_to_dlq_at", datetime.now(timezone.utc).isoformat())
        body.setdefault("resolved", False)
        await self.col.insert_one(body)
        body.pop("_id", None)
        return body

    async def list_unresolved(self, *, limit: int = 100) -> list[dict]:
        cursor = self.col.find(
            {"tenant_id": self.tenant_id, "resolved": False},
            {"_id": 0},
        ).sort("moved_to_dlq_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def mark_resolved(self, dlq_id: str, *, action: str, user_id: str) -> Optional[dict]:
        now = datetime.now(timezone.utc).isoformat()
        await self.col.update_one(
            {"id": dlq_id, "tenant_id": self.tenant_id, "resolved": False},
            {"$set": {
                "resolved": True, "resolved_action": action,
                "resolved_by": user_id, "resolved_at": now,
            }},
        )
        return await self.col.find_one(
            {"id": dlq_id, "tenant_id": self.tenant_id}, {"_id": 0},
        )


class WebhookPendingQueueRepository(BaseRepository):
    """Cola Mongo simple — sustituye Redis Streams.

    Cada doc representa un job pendiente. El worker hace findOneAndUpdate
    con `claimed_at` para reservar el job (atómico). Tras delivery
    success/permanent failure → delete. En reintento → set next_run_at.
    """
    collection_name = "webhook_pending_queue"

    async def enqueue(self, doc: dict) -> dict:
        body = dict(doc)
        body.setdefault("id", new_id())
        body["tenant_id"] = self.tenant_id
        now = datetime.now(timezone.utc).isoformat()
        body.setdefault("enqueued_at", now)
        body.setdefault("next_run_at", now)
        body.setdefault("attempt_number", 0)
        body.setdefault("claimed_at", None)
        await self.col.insert_one(body)
        body.pop("_id", None)
        return body

    async def claim_due(self, *, batch: int = 25) -> list[dict]:
        """Reclama hasta `batch` jobs cuyo next_run_at <= ahora.

        Atómico: marca `claimed_at` para evitar double-claim entre workers.
        """
        now = datetime.now(timezone.utc).isoformat()
        claimed: list[dict] = []
        for _ in range(batch):
            doc = await self.col.find_one_and_update(
                {"$and": [
                    {"next_run_at": {"$lte": now}},
                    {"$or": [{"claimed_at": None}, {"claimed_at": {"$exists": False}}]},
                ]},
                {"$set": {"claimed_at": now}},
                projection={"_id": 0},
                return_document=True,
            )
            if doc is None:
                break
            claimed.append(doc)
        return claimed

    async def reschedule(self, job_id: str, *, next_run_at: str,
                         attempt_number: int) -> int:
        r = await self.col.update_one(
            {"id": job_id},
            {"$set": {
                "next_run_at": next_run_at,
                "attempt_number": attempt_number,
                "claimed_at": None,
            }},
        )
        return r.modified_count

    async def delete(self, job_id: str) -> int:
        r = await self.col.delete_one({"id": job_id})
        return r.deleted_count
