"""Append-only collections — R04 + R27.

``timeline_events`` and ``cae_audit_log`` accept INSERTs only.
Any code that imports this module gets a hard error if it tries UPDATE/DELETE.
"""
from __future__ import annotations
from datetime import datetime, timezone

from core.db import get_db
from core.uuid import new_id


class _AppendOnlyRepository:
    collection_name: str = ""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    @property
    def col(self):
        return get_db()[self.collection_name]

    async def append(self, doc: dict) -> dict:
        body = dict(doc)
        body["id"] = new_id()
        body["tenant_id"] = self.tenant_id
        body["created_at"] = datetime.now(timezone.utc).isoformat()
        await self.col.insert_one(body)
        body.pop("_id", None)
        return body

    async def list(self, query: dict, *, limit: int = 200) -> list[dict]:
        q = dict(query)
        q["tenant_id"] = self.tenant_id
        cursor = self.col.find(q, {"_id": 0}).sort("created_at", 1).limit(limit)
        return await cursor.to_list(length=limit)

    # R04 / R27: deliberately NO update / delete methods.


class TimelineRepository(_AppendOnlyRepository):
    collection_name = "timeline_events"

    async def record(
        self,
        *,
        ticket_id: str,
        event_type: str,
        actor_type: str,
        actor_id: str | None = None,
        channel: str | None = None,
        payload: dict | None = None,
    ) -> dict:
        return await self.append({
            "ticket_id": ticket_id,
            "event_type": event_type,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "channel": channel,
            "payload": payload or {},
        })


class CaeAuditRepository(_AppendOnlyRepository):
    collection_name = "cae_audit_log"

    async def record(
        self,
        *,
        user_id: str,
        action: str,  # create | update | delete | test
        entity: str,
        entity_id: str | None = None,
        before_json: dict | None = None,
        after_json: dict | None = None,
    ) -> dict:
        if action not in {"create", "update", "delete", "test", "reclassify"}:
            raise ValueError(f"Invalid CAE audit action: {action}")
        return await self.append({
            "user_id": user_id,
            "action": action,
            "entity": entity,
            "entity_id": entity_id,
            "before_json": before_json,
            "after_json": after_json,
        })
