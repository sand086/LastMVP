"""Projects repository — tenant-scoped (R01)."""
from __future__ import annotations
from datetime import datetime, timezone

from .base import BaseRepository


class ProjectRepository(BaseRepository):
    collection_name = "projects"

    async def create(self, *, name: str, status: str = "active") -> dict:
        return await self.insert({
            "name": name,
            "status": status,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
