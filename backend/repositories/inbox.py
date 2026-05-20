"""In-app notifications repository — PROMPT 13 P1.2.

Notificaciones efímeras que se renderizan como badge/dropdown en la UI.
Modelo simple: append-only; el `read_at` se set on read.

Schema:
  {id, tenant_id, recipient_user_id, kind, title, body, link, payload,
   created_at, read_at?}
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from core.uuid import new_id
from repositories.base import BaseRepository


class InboxRepository(BaseRepository):
    collection_name = "inbox_notifications"

    async def push(self, *, recipient_user_id: str, kind: str, title: str,
                   body: str = "", link: Optional[str] = None,
                   payload: Optional[dict] = None) -> dict:
        return await self.insert({
            "id": new_id(),
            "recipient_user_id": recipient_user_id,
            "kind": kind, "title": title, "body": body, "link": link,
            "payload": payload or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "read_at": None,
        })

    async def push_to_role(self, *, role: str, kind: str, title: str,
                           body: str = "", link: Optional[str] = None,
                           payload: Optional[dict] = None) -> int:
        """Push the same notification to every active user with `role` in the tenant."""
        users = await self.col.database.users.find(
            {"tenant_id": self.tenant_id, "role": role, "status": "active"},
            {"_id": 0, "id": 1},
        ).to_list(length=500)
        for u in users:
            await self.push(recipient_user_id=u["id"], kind=kind, title=title,
                            body=body, link=link, payload=payload)
        return len(users)

    async def list_for(self, *, user_id: str, only_unread: bool = False,
                       limit: int = 30) -> list[dict]:
        q: dict = {"recipient_user_id": user_id}
        if only_unread:
            q["read_at"] = None
        return await self.find(q, sort=[("created_at", -1)], limit=limit)

    async def count_unread(self, *, user_id: str) -> int:
        return await self.col.count_documents({
            "tenant_id": self.tenant_id,
            "recipient_user_id": user_id, "read_at": None,
        })

    async def mark_read(self, *, user_id: str, notif_id: str) -> bool:
        result = await self.col.update_one(
            {"tenant_id": self.tenant_id, "id": notif_id, "recipient_user_id": user_id},
            {"$set": {"read_at": datetime.now(timezone.utc).isoformat()}},
        )
        return result.modified_count > 0

    async def mark_all_read(self, *, user_id: str) -> int:
        result = await self.col.update_many(
            {"tenant_id": self.tenant_id, "recipient_user_id": user_id, "read_at": None},
            {"$set": {"read_at": datetime.now(timezone.utc).isoformat()}},
        )
        return result.modified_count
