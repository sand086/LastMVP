"""Subclients repository — tenant-scoped."""
from __future__ import annotations
from datetime import datetime, timezone

from .base import BaseRepository


class SubclientRepository(BaseRepository):
    collection_name = "subclients"

    async def create(self, *, client_id: str, name: str, status: str = "active") -> dict:
        return await self.insert({
            "client_id": client_id,
            "name": name,
            "status": status,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
