"""Users + auth lookup helpers."""
from __future__ import annotations
from datetime import datetime, timezone

from core.db import get_db
from core.security import hash_password
from core.uuid import new_id


class UserRepository:
    """Users live across tenants (each user belongs to ONE tenant)."""

    @property
    def col(self):
        return get_db()["users"]

    async def by_email(self, email: str) -> dict | None:
        return await self.col.find_one({"email": email.lower()})

    async def by_id(self, user_id: str, tenant_id: str | None = None) -> dict | None:
        q = {"id": user_id}
        if tenant_id is not None:
            q["tenant_id"] = tenant_id
        return await self.col.find_one(q, {"_id": 0, "password_hash": 0})

    async def create(self, *, tenant_id: str, email: str, password: str, name: str,
                     role: str, status: str = "active") -> dict:
        doc = {
            "id": new_id(),
            "tenant_id": tenant_id,
            "email": email.lower(),
            "password_hash": hash_password(password),
            "name": name,
            "role": role,
            "status": status,
            "last_login_at": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.col.insert_one(doc)
        doc.pop("_id", None)
        doc.pop("password_hash", None)
        return doc

    async def update_password(self, user_id: str, new_password: str) -> int:
        r = await self.col.update_one(
            {"id": user_id},
            {"$set": {"password_hash": hash_password(new_password)}},
        )
        return r.modified_count

    async def touch_login(self, user_id: str) -> None:
        await self.col.update_one(
            {"id": user_id},
            {"$set": {"last_login_at": datetime.now(timezone.utc).isoformat()}},
        )
