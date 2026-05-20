"""Motivos + Soluciones repositories — tenant-scoped (R01)."""
from __future__ import annotations
from datetime import datetime, timezone

from .base import BaseRepository


class MotivoRepository(BaseRepository):
    collection_name = "motivos"

    async def create(self, *, code: str, name: str, restricted: bool, active: bool) -> dict:
        return await self.insert({
            "code": code,
            "name": name,
            "restricted": restricted,
            "active": active,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    async def by_code(self, code: str) -> dict | None:
        return await self.find_one({"code": code})


class SolucionRepository(BaseRepository):
    collection_name = "soluciones"

    async def create(self, *, motivo_id: str, name: str, steps: list,
                     template_email: str | None, template_wa: str | None,
                     automatable: bool) -> dict:
        return await self.insert({
            "motivo_id": motivo_id,
            "name": name,
            "steps": steps,
            "template_email": template_email,
            "template_wa": template_wa,
            "automatable": automatable,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
