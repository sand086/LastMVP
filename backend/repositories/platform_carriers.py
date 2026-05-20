"""Platform-level carrier configurations (root_dev only).

SaaS hierarchy resolved at request time:
    subclient.carriers.<code>  (future)
       ↓
    client.carriers.<code>     (already exists)
       ↓
    project.carriers.<code>    (future)
       ↓
    tenant.carriers (collection) — `api_creds_ref` overrides platform
       ↓
    platform_carrier_configs.<code>  ← THIS REPO (read-only for tenants)
"""
from __future__ import annotations
from datetime import datetime, timezone

from core.crypto import encrypt, decrypt
from .base import BaseRepository


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlatformCarrierRepository(BaseRepository):
    """Cross-tenant collection — only root_dev / superadmin can read or write
    the secret material. Tenants observe inheritance via the resolver.

    Document shape:
      {
        "id": <new_id>, "code": "routal", "name": "Routal" | None,
        "api_key_ref": <Fernet|None>, "client_secret_ref": <Fernet|None>,
        "base_url": "https://...", "enabled": bool,
        "billing_mode": "platform_pays" | "tenant_pays_overage",
        "tenant_access": {
          "<tenant_id>": {
            "project_ids": [...],
            "rate_limit_per_min": int | None,
            "enabled": bool,
            "granted_at": iso,
          },
        },
        "created_at": iso, "updated_at": iso,
      }

    `code` is unique. Inserts upsert by `code`.
    """
    collection_name = "platform_carrier_configs"

    def __init__(self) -> None:
        super().__init__(tenant_id=None)  # NOT tenant-scoped

    async def get(self, code: str) -> dict | None:
        return await self.find_one({"code": code.lower()})

    async def list_all(self) -> list[dict]:
        cur = self.col.find({}, {"_id": 0})
        return [doc async for doc in cur]

    async def upsert(self, code: str, patch: dict) -> dict:
        code = code.lower()
        existing = await self.get(code) or {}
        merged = dict(existing)

        # Secrets — encrypt or wipe to None.
        if "api_key" in patch:
            v = patch["api_key"]
            merged["api_key_ref"] = encrypt(v) if v else None
        if "client_secret" in patch:
            v = patch["client_secret"]
            merged["client_secret_ref"] = encrypt(v) if v else None

        for k in ("name", "base_url", "billing_mode", "enabled"):
            if k in patch and patch[k] is not None:
                merged[k] = patch[k]

        merged["updated_at"] = _now_iso()
        merged["code"] = code
        merged.setdefault("created_at", _now_iso())
        merged.setdefault("tenant_access", {})
        merged.setdefault("enabled", True)
        merged.setdefault("billing_mode", "platform_pays")

        await self.col.update_one(
            {"code": code}, {"$set": merged}, upsert=True)
        return public_view(merged)

    async def delete(self, code: str) -> bool:
        result = await self.col.delete_one({"code": code.lower()})
        return result.deleted_count > 0

    async def grant_access(self, code: str, tenant_id: str, *,
                            project_ids: list[str] | None = None,
                            rate_limit_per_min: int | None = None,
                            enabled: bool = True) -> dict | None:
        existing = await self.get(code)
        if not existing:
            return None
        access = existing.get("tenant_access") or {}
        access[tenant_id] = {
            "project_ids": project_ids or [],
            "rate_limit_per_min": rate_limit_per_min,
            "enabled": enabled,
            "granted_at": _now_iso(),
        }
        await self.col.update_one(
            {"code": code.lower()},
            {"$set": {"tenant_access": access, "updated_at": _now_iso()}})
        return public_view({**existing, "tenant_access": access})

    async def revoke_access(self, code: str, tenant_id: str) -> bool:
        result = await self.col.update_one(
            {"code": code.lower()},
            {"$unset": {f"tenant_access.{tenant_id}": ""},
             "$set": {"updated_at": _now_iso()}})
        return result.modified_count > 0

    async def get_decrypted(self, code: str) -> dict | None:
        """Returns the in-use config (plaintext secrets) for the resolver/adapter.
        Returns None if no config or disabled."""
        cfg = await self.get(code)
        if not cfg or cfg.get("enabled") is False:
            return None
        out = {
            "code": cfg.get("code"),
            "name": cfg.get("name"),
            "base_url": cfg.get("base_url"),
            "billing_mode": cfg.get("billing_mode", "platform_pays"),
            "enabled": cfg.get("enabled", True),
            "tenant_access": cfg.get("tenant_access") or {},
            "api_key": None, "client_secret": None,
        }
        for src, dst in (("api_key_ref", "api_key"),
                          ("client_secret_ref", "client_secret")):
            ref = cfg.get(src)
            if ref:
                try:
                    out[dst] = decrypt(ref)
                except ValueError:
                    out[dst] = None
        return out


def public_view(cfg: dict) -> dict:
    """Strip secrets for the wire; returns api_key_set / client_secret_set bools."""
    if not cfg:
        return {}
    out = {k: v for k, v in cfg.items()
           if k not in {"_id", "api_key_ref", "client_secret_ref"}}
    out["api_key_set"] = bool(cfg.get("api_key_ref"))
    out["client_secret_set"] = bool(cfg.get("client_secret_ref"))
    return out
