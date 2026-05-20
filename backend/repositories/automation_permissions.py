"""Automation permissions matrix — tenant-scoped (R01) + R03 default-deny."""
from __future__ import annotations
from datetime import datetime, timezone

from core.uuid import new_id

from .base import BaseRepository


class AutomationPermissionRepository(BaseRepository):
    collection_name = "automation_permissions"

    async def upsert(self, *, client_id: str, solucion_id: str,
                     channel: str, allowed: bool) -> dict:
        """(client_id, solucion_id, channel) is unique inside a tenant.

        Default behaviour absent any row = DENIED (R03). This method is the
        ONLY way to flip a permission on/off — admin/coordinator only.
        """
        now = datetime.now(timezone.utc).isoformat()
        await self.col.update_one(
            {"tenant_id": self.tenant_id, "client_id": client_id,
             "solucion_id": solucion_id, "channel": channel},
            {
                "$set": {"allowed": allowed, "updated_at": now},
                "$setOnInsert": {
                    "id": new_id(),
                    "tenant_id": self.tenant_id,
                    "client_id": client_id,
                    "solucion_id": solucion_id,
                    "channel": channel,
                    "created_at": now,
                },
            },
            upsert=True,
        )
        return await self.col.find_one(
            {"tenant_id": self.tenant_id, "client_id": client_id,
             "solucion_id": solucion_id, "channel": channel},
            {"_id": 0},
        )

    async def find_for_client(self, client_id: str) -> list[dict]:
        cursor = self.col.find(
            {"tenant_id": self.tenant_id, "client_id": client_id},
            {"_id": 0},
        ).sort("solucion_id", 1)
        return await cursor.to_list(length=2000)
