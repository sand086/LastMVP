"""Carriers repository — tenant-scoped + credential encryption (R07)."""
from __future__ import annotations
from datetime import datetime, timezone

from core.crypto import encrypt

from .base import BaseRepository


class CarrierRepository(BaseRepository):
    collection_name = "carriers"

    async def create(self, *, name: str, code: str, has_api: bool,
                     api_url: str | None, api_creds: str | None,
                     pulling_supported: bool, webhook_supported: bool,
                     status: str = "active") -> dict:
        return await self.insert({
            "name": name,
            "code": code,
            "has_api": has_api,
            "api_url": api_url,
            "api_creds_ref": encrypt(api_creds) if api_creds else None,
            "pulling_supported": pulling_supported,
            "webhook_supported": webhook_supported,
            "status": status,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    async def update_with_secret(self, carrier_id: str, updates: dict) -> int:
        body = dict(updates)
        if "api_creds" in body:
            raw = body.pop("api_creds")
            body["api_creds_ref"] = encrypt(raw) if raw else None
        if not body:
            return 0
        return await self.update_one({"id": carrier_id}, body)


def public_view(carrier_doc: dict) -> dict:
    redacted = dict(carrier_doc)
    if "api_creds_ref" in redacted:
        redacted["api_creds_set"] = bool(redacted["api_creds_ref"])
        redacted.pop("api_creds_ref", None)
    return redacted
