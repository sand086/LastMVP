"""AI repositories — colecciones MongoDB del módulo Configuración IA (PROMPT 26).

Colecciones:
  - ai_features                 catálogo (tenant_id NULL = global MyE)
  - ai_pricing_brackets         tarifas
  - ai_client_config            configuración por cliente (opt-in R39)
  - ai_invocation_log           audit trail APPEND-ONLY (R37)
  - ai_consumption_monthly      acumulado por cliente / mes (topes)
"""
from __future__ import annotations
from datetime import datetime, timezone

from core.db import get_db
from core.uuid import new_id
from repositories.base import BaseRepository


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ────────────────────── ai_features (catálogo global) ────────────────────
class AIFeatureRepository(BaseRepository):
    """Catálogo de features. tenant_id puede ser NULL (global) o de un tenant."""
    collection_name = "ai_features"

    def __init__(self, tenant_id: str | None = None):
        # admite global (None) o por tenant
        super().__init__(tenant_id=tenant_id)

    def _scope(self, query: dict | None = None) -> dict:
        # Para features queremos: tenant_id=None (global) OR tenant_id=self.tenant_id
        q = dict(query or {})
        if self.tenant_id is None:
            return q
        if "tenant_id" in q:
            return q
        q["$or"] = [{"tenant_id": None}, {"tenant_id": self.tenant_id}]
        return q

    async def insert(self, doc: dict) -> dict:
        body = dict(doc)
        body.setdefault("id", new_id())
        # tenant_id se preserva tal cual venga (puede ser None para global)
        body.setdefault("tenant_id", self.tenant_id)
        body["created_at"] = _now_iso()
        body["updated_at"] = _now_iso()
        await self.col.insert_one(body)
        body.pop("_id", None)
        return body

    async def by_code(self, feature_code: str) -> dict | None:
        return await self.col.find_one(
            self._scope({"feature_code": feature_code}), {"_id": 0}
        )

    async def update_by_id(self, feature_id: str, updates: dict) -> int:
        updates = {**updates, "updated_at": _now_iso()}
        result = await self.col.update_one(
            self._scope({"id": feature_id}), {"$set": updates}
        )
        return result.modified_count


# ────────────────────── ai_pricing_brackets (global) ─────────────────────
class AIBracketRepository(BaseRepository):
    """Brackets son globales (no tenant-scoped). Sólo root_dev/superadmin gestionan."""
    collection_name = "ai_pricing_brackets"

    def __init__(self):
        super().__init__(tenant_id=None)

    async def insert(self, doc: dict) -> dict:
        body = dict(doc)
        body.setdefault("id", new_id())
        body["created_at"] = _now_iso()
        await self.col.insert_one(body)
        body.pop("_id", None)
        return body

    async def by_name(self, name: str) -> dict | None:
        return await self.col.find_one({"bracket_name": name}, {"_id": 0})

    async def list_all(self) -> list[dict]:
        cur = self.col.find({}, {"_id": 0}).sort("monthly_fee_usd", 1)
        return await cur.to_list(length=200)


# ────────────────────── ai_client_config (por cliente) ───────────────────
class AIClientConfigRepository(BaseRepository):
    """Config por cliente. R39: is_active default false; opt-in explícito requerido."""
    collection_name = "ai_client_config"

    async def get(self, client_id: str) -> dict | None:
        return await self.find_one({"client_id": client_id})

    async def upsert(self, payload: dict) -> dict:
        client_id = payload["client_id"]
        existing = await self.get(client_id)
        if existing:
            updates = {**payload, "updated_at": _now_iso()}
            await self.col.update_one(
                self._scope({"client_id": client_id}),
                {"$set": updates},
            )
            return await self.get(client_id)
        body = {
            "id": new_id(),
            "tenant_id": self.tenant_id,
            "is_active": False,
            "enabled_features": [],
            "rollover_enabled": False,
            "monthly_cap_override_usd": None,
            "opt_in_signature": None,
            "opt_in_at": None,
            "opt_out_at": None,
            "opt_out_reason": None,
            "custom_provider": None,
            "custom_api_key_present": False,
            "custom_api_key_encrypted": None,
            **payload,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        await self.col.insert_one(body)
        body.pop("_id", None)
        return body

    async def opt_out(self, client_id: str, reason: str) -> bool:
        result = await self.col.update_one(
            self._scope({"client_id": client_id}),
            {"$set": {
                "is_active": False,
                "opt_out_at": _now_iso(),
                "opt_out_reason": reason,
                "updated_at": _now_iso(),
            }},
        )
        return result.modified_count > 0


# ────────────────────── ai_invocation_log (APPEND-ONLY · R37) ────────────
class AIInvocationLogRepository(BaseRepository):
    """R37: append-only — exponemos sólo append() y query()."""
    collection_name = "ai_invocation_log"

    async def append(self, doc: dict) -> dict:
        body = {
            "id": new_id(),
            "tenant_id": self.tenant_id,
            "created_at": _now_iso(),
            **doc,
        }
        await self.col.insert_one(body)
        body.pop("_id", None)
        return body

    async def query(self, query: dict | None = None, *, limit: int = 200) -> list[dict]:
        q = self._scope(query or {})
        cur = self.col.find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
        return await cur.to_list(length=limit)


# ────────────────────── ai_consumption_monthly (topes) ───────────────────
class AIConsumptionRepository(BaseRepository):
    collection_name = "ai_consumption_monthly"

    @staticmethod
    def _yyyymm(now: datetime | None = None) -> str:
        d = now or datetime.now(timezone.utc)
        return d.strftime("%Y-%m")

    async def get_or_init(self, client_id: str, *, year_month: str | None = None) -> dict:
        ym = year_month or self._yyyymm()
        doc = await self.find_one({"client_id": client_id, "year_month": ym})
        if doc:
            return doc
        return await self.insert({
            "client_id": client_id,
            "year_month": ym,
            "invocations_count": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": 0.0,
            "alert_80_sent_at": None,
            "alert_100_sent_at": None,
            "updated_at": _now_iso(),
        })

    async def add_consumption(
        self,
        client_id: str,
        *,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ) -> dict:
        ym = self._yyyymm()
        await self.col.update_one(
            self._scope({"client_id": client_id, "year_month": ym}),
            {
                "$inc": {
                    "invocations_count": 1,
                    "total_input_tokens": input_tokens,
                    "total_output_tokens": output_tokens,
                    "total_cost_usd": cost_usd,
                },
                "$set": {"updated_at": _now_iso()},
                "$setOnInsert": {
                    "id": new_id(),
                    "tenant_id": self.tenant_id,
                    "alert_80_sent_at": None,
                    "alert_100_sent_at": None,
                },
            },
            upsert=True,
        )
        return await self.find_one({"client_id": client_id, "year_month": ym})

    async def mark_alert_sent(self, client_id: str, *, threshold: int) -> None:
        field = "alert_80_sent_at" if threshold == 80 else "alert_100_sent_at"
        await self.col.update_one(
            self._scope({"client_id": client_id, "year_month": self._yyyymm()}),
            {"$set": {field: _now_iso(), "updated_at": _now_iso()}},
        )


async def ensure_ai_indexes() -> None:
    db = get_db()
    await db.ai_features.create_index("feature_code", unique=True)
    await db.ai_pricing_brackets.create_index("bracket_name", unique=True)
    await db.ai_client_config.create_index(
        [("tenant_id", 1), ("client_id", 1)], unique=True,
        name="uq_ai_client_per_tenant",
    )
    await db.ai_invocation_log.create_index(
        [("tenant_id", 1), ("client_id", 1), ("created_at", -1)],
        name="ix_invlog_tenant_client_ts",
    )
    await db.ai_consumption_monthly.create_index(
        [("tenant_id", 1), ("client_id", 1), ("year_month", 1)], unique=True,
        name="uq_consumption_client_month",
    )
