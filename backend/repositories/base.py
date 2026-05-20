"""Base repository — enforces R01 (multi-tenant isolation) and R19 (UUID PKs).

Every concrete repository extends this and uses the helpers below to access
its collection. The helpers reject any query that does not include
``tenant_id``.

Tests under /app/tests/test_multi_tenant_isolation.py validate this contract.
"""
from __future__ import annotations

from core.db import get_db
from core.uuid import new_id


class BaseRepository:
    collection_name: str = ""

    def __init__(self, tenant_id: str | None = None):
        # tenant_id may be None ONLY for the ``tenants`` collection (cross-tenant by nature)
        self.tenant_id = tenant_id

    @property
    def col(self):
        if not self.collection_name:
            raise RuntimeError(f"{self.__class__.__name__} missing collection_name")
        return get_db()[self.collection_name]

    def _scope(self, query: dict | None = None) -> dict:
        """R01: every read/update/delete must filter by tenant_id.

        Bootstrap rule: this method REFUSES to return a query without
        ``tenant_id`` unless self.tenant_id is None (cross-tenant collections).
        """
        q = dict(query or {})
        if self.tenant_id is None:
            return q
        if "tenant_id" in q and q["tenant_id"] != self.tenant_id:
            # Cross-tenant attempt — translate to "no match" (R08: 404 not 403)
            q["tenant_id"] = "__never_matches__"
            return q
        q["tenant_id"] = self.tenant_id
        return q

    async def find_one(self, query: dict | None = None, projection: dict | None = None):
        proj = projection or {"_id": 0}
        return await self.col.find_one(self._scope(query), proj)

    async def find(self, query: dict | None = None, projection: dict | None = None,
                   limit: int = 100, skip: int = 0, sort: list | None = None):
        proj = projection or {"_id": 0}
        cursor = self.col.find(self._scope(query), proj).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        return await cursor.to_list(length=limit)

    async def count(self, query: dict | None = None) -> int:
        return await self.col.count_documents(self._scope(query))

    async def insert(self, doc: dict) -> dict:
        body = dict(doc)
        body.setdefault("id", new_id())
        if self.tenant_id is not None:
            body["tenant_id"] = self.tenant_id
        await self.col.insert_one(body)
        # Strip Mongo's _id which insert_one mutates onto the dict
        body.pop("_id", None)
        return body

    async def update_one(self, query: dict, updates: dict) -> int:
        result = await self.col.update_one(self._scope(query), {"$set": updates})
        return result.modified_count

    async def delete_one(self, query: dict) -> int:
        result = await self.col.delete_one(self._scope(query))
        return result.deleted_count
