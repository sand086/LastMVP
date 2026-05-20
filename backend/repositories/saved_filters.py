"""Saved filters por usuario (PROMPT 03 backlog).

Permite a cada usuario guardar combinaciones de filtros nombradas para
reutilizarlas en el panel /agente. Scope: tenant_id + user_id.
"""
from __future__ import annotations
from datetime import datetime, timezone

from core.uuid import new_id

from .base import BaseRepository


class SavedFilterRepository(BaseRepository):
    collection_name = "saved_filters"

    async def list_for_user(self, user_id: str) -> list[dict]:
        cursor = self.col.find(
            {"tenant_id": self.tenant_id, "user_id": user_id},
            {"_id": 0},
        ).sort("created_at", -1).limit(50)
        return await cursor.to_list(length=50)

    async def create(self, *, user_id: str, name: str, scope: str,
                      filters: dict) -> dict:
        body = {
            "id": new_id(),
            "tenant_id": self.tenant_id,
            "user_id": user_id,
            "name": name.strip()[:60],
            "scope": scope,  # "agent_queue" | "admin_tickets" | "claims"
            "filters": filters or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.col.insert_one(body)
        body.pop("_id", None)
        return body

    async def delete(self, filter_id: str, user_id: str) -> int:
        r = await self.col.delete_one({
            "id": filter_id, "tenant_id": self.tenant_id, "user_id": user_id,
        })
        return r.deleted_count
