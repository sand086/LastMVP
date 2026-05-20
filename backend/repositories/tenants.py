"""Tenants repository — cross-tenant by nature.

Tenants don't have a parent ``tenant_id`` (they ARE the tenant).
Initialize with ``tenant_id=None`` so the base scope is bypassed.
"""
from __future__ import annotations
from datetime import datetime, timezone

from .base import BaseRepository


class TenantRepository(BaseRepository):
    collection_name = "tenants"

    def __init__(self):
        super().__init__(tenant_id=None)

    async def create(self, *, name: str, slug: str, status: str = "active") -> dict:
        return await self.insert({
            "name": name,
            "slug": slug,
            "status": status,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    async def by_slug(self, slug: str) -> dict | None:
        return await self.col.find_one({"slug": slug}, {"_id": 0})

    async def set_status(self, tenant_id: str, status: str) -> int:
        r = await self.col.update_one({"id": tenant_id}, {"$set": {"status": status}})
        return r.modified_count
