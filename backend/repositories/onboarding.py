"""AdminOnboardingRepository — Bundle E · persistence per user×tenant.

Estructura del doc en `admin_onboarding_progress`:
    {
      id:                str,                   # uuid
      tenant_id:         str,
      user_id:           str,
      current_step:      str,
      steps_completed:   list[str],
      step_data:         dict,                  # payloads parciales
      started_at:        ISO str,
      last_activity:     ISO str,
      completed_at:      ISO str | None,
      abandoned:         bool,                  # cron lo marca tras 7d
    }

Unique compound index sobre (tenant_id, user_id) — un wizard por user×tenant.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from core.uuid import new_id
from models.onboarding import STEP_ORDER, STEP_WELCOME

from .base import BaseRepository


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AdminOnboardingRepository(BaseRepository):
    collection_name = "admin_onboarding_progress"

    _INDEX_READY = False

    async def ensure_index(self) -> None:
        if AdminOnboardingRepository._INDEX_READY:
            return
        await self.col.create_index(
            [("tenant_id", 1), ("user_id", 1)], unique=True,
        )
        await self.col.create_index([("completed_at", 1)])
        await self.col.create_index([("abandoned", 1), ("last_activity", 1)])
        AdminOnboardingRepository._INDEX_READY = True

    async def get_for_user(self, user_id: str) -> Optional[dict]:
        return await self.find_one({"user_id": user_id})

    async def start_if_absent(self, user_id: str) -> dict:
        existing = await self.get_for_user(user_id)
        if existing:
            return existing
        return await self.insert({
            "id": new_id(),
            "user_id": user_id,
            "current_step": STEP_WELCOME,
            "steps_completed": [],
            "step_data": {},
            "started_at": _now_iso(),
            "last_activity": _now_iso(),
            "completed_at": None,
            "abandoned": False,
        })

    async def mark_step(
        self, *, user_id: str, completed_step: str,
        step_data: dict | None, next_step: str | None,
    ) -> dict:
        """Append `completed_step` to `steps_completed`, merge step_data,
        and update `current_step`."""
        doc = await self.get_for_user(user_id) or await self.start_if_absent(user_id)
        steps = list(doc.get("steps_completed") or [])
        if completed_step not in steps:
            steps.append(completed_step)
        merged_data = dict(doc.get("step_data") or {})
        if step_data:
            merged_data.update(step_data)
        new_current = next_step or doc.get("current_step")
        await self.col.update_one(
            {"id": doc["id"], "tenant_id": self.tenant_id},
            {"$set": {
                "steps_completed": steps,
                "step_data": merged_data,
                "current_step": new_current,
                "last_activity": _now_iso(),
            }},
        )
        return await self.get_for_user(user_id)

    async def mark_completed(self, user_id: str) -> dict:
        doc = await self.get_for_user(user_id)
        if not doc:
            doc = await self.start_if_absent(user_id)
        await self.col.update_one(
            {"id": doc["id"], "tenant_id": self.tenant_id},
            {"$set": {
                "completed_at": _now_iso(),
                "last_activity": _now_iso(),
                "current_step": None,
            }},
        )
        return await self.get_for_user(user_id)


def compute_next_step(current_step: str, steps_completed: list[str]) -> Optional[str]:
    """Devuelve el siguiente paso del flujo. None si ya está todo cubierto."""
    try:
        idx = STEP_ORDER.index(current_step)
    except ValueError:
        return STEP_ORDER[0]
    # Saltar pasos que ya están completados (caso 2do admin del tenant).
    for cand in STEP_ORDER[idx + 1:]:
        if cand not in steps_completed:
            return cand
    return None
