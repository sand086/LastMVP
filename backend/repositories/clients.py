"""Clients repository — tenant-scoped + credential encryption (R01 + R07)."""
from __future__ import annotations
import secrets
from datetime import datetime, timezone

from core.crypto import encrypt, decrypt
from core.errors import ResourceNotFoundException

from .base import BaseRepository


class ClientRepository(BaseRepository):
    collection_name = "clients"

    async def create(self, *, project_id: str, name: str, ingest_mode: str,
                     api_url: str | None, api_auth_type: str, api_creds: str | None,
                     pulling_freq_min: int, preferred_channel: str,
                     ops_contact_name: str | None, ops_contact_email: str | None,
                     ops_contact_wa: str | None,
                     cxc_contact_name: str | None = None,
                     cxc_contact_email: str | None = None,
                     status_map: dict | None = None) -> dict:
        webhook_token = secrets.token_urlsafe(32)
        creds_ref = encrypt(api_creds) if api_creds else None
        return await self.insert({
            "project_id": project_id,
            "name": name,
            "ingest_mode": ingest_mode,
            "webhook_token": webhook_token,
            "api_url": api_url,
            "api_auth_type": api_auth_type,
            "api_creds_ref": creds_ref,
            "pulling_freq_min": pulling_freq_min,
            "preferred_channel": preferred_channel,
            "ops_contact_name": ops_contact_name,
            "ops_contact_email": ops_contact_email,
            "ops_contact_wa": ops_contact_wa,
            "cxc_contact_name": cxc_contact_name,
            "cxc_contact_email": cxc_contact_email,
            "status_map": status_map or {},
            "carriers": {},  # per-client carrier configs (Routal multi-project, etc.)
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    async def update_with_secret(self, client_id: str, updates: dict) -> int:
        """``api_creds`` is plaintext on the wire; persist as encrypted ``api_creds_ref``."""
        body = dict(updates)
        if "api_creds" in body:
            raw = body.pop("api_creds")
            body["api_creds_ref"] = encrypt(raw) if raw else None
        if not body:
            return 0
        return await self.update_one({"id": client_id}, body)

    # ─── Per-client carrier configuration (multi-project SaaS) ─────────
    async def set_carrier_config(self, client_id: str, carrier_code: str,
                                  patch: dict) -> dict:
        """Merge a partial config into ``clients.carriers.<carrier_code>``.

        ``patch`` keys understood (all optional):
          - api_key            (plaintext on wire; stored as api_key_ref)
          - project_ids        list[str]
          - default_project_id str
          - base_url           str
          - enabled            bool

        Returns the resulting config as it lives in the DB (api_key replaced
        by api_key_set: bool).
        """
        carrier_code = carrier_code.lower()
        client = await self.find_one({"id": client_id})
        if not client:
            raise ResourceNotFoundException("Cliente no encontrado.")
        current = (client.get("carriers") or {}).get(carrier_code, {})
        merged = dict(current)
        if "api_key" in patch:
            api_key = patch["api_key"]
            merged["api_key_ref"] = encrypt(api_key) if api_key else None
        for k in ("project_ids", "default_project_id", "base_url", "enabled"):
            if k in patch and patch[k] is not None:
                merged[k] = patch[k]
        # If default_project_id is set but not in project_ids, append it
        pids = merged.get("project_ids") or []
        dpid = merged.get("default_project_id")
        if dpid and dpid not in pids:
            merged["project_ids"] = [dpid, *pids]
        merged["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.update_one({"id": client_id},
                              {f"carriers.{carrier_code}": merged})
        return _carrier_cfg_public(merged)

    async def get_carrier_config(self, client_id: str, carrier_code: str
                                  ) -> dict | None:
        """Returns the decrypted, in-use config (api_key in clear) for the
        scheduler / adapter. Returns None if no config exists or disabled."""
        carrier_code = carrier_code.lower()
        client = await self.find_one({"id": client_id})
        if not client:
            return None
        cfg = (client.get("carriers") or {}).get(carrier_code)
        if not cfg or cfg.get("enabled") is False:
            return None
        out = {
            "project_ids": cfg.get("project_ids") or [],
            "default_project_id": cfg.get("default_project_id"),
            "base_url": cfg.get("base_url") or "https://api.routal.com",
            "enabled": cfg.get("enabled", True),
            "api_key": None,
        }
        ref = cfg.get("api_key_ref")
        if ref:
            try:
                out["api_key"] = decrypt(ref)
            except ValueError:
                out["api_key"] = None
        return out

    async def get_carrier_config_public(self, client_id: str, carrier_code: str
                                         ) -> dict | None:
        """Front-end safe view (no api_key, only api_key_set bool)."""
        carrier_code = carrier_code.lower()
        client = await self.find_one({"id": client_id})
        if not client:
            return None
        cfg = (client.get("carriers") or {}).get(carrier_code)
        if not cfg:
            return None
        return _carrier_cfg_public(cfg)

    async def delete_carrier_config(self, client_id: str, carrier_code: str
                                     ) -> bool:
        carrier_code = carrier_code.lower()
        result = await self.col.update_one(
            self._scope({"id": client_id}),
            {"$unset": {f"carriers.{carrier_code}": ""}},
        )
        return result.modified_count > 0


def _carrier_cfg_public(cfg: dict) -> dict:
    out = {k: v for k, v in (cfg or {}).items() if k != "api_key_ref"}
    out["api_key_set"] = bool((cfg or {}).get("api_key_ref"))
    return out


def public_view(client_doc: dict) -> dict:
    """Strip secrets before returning to the client."""
    redacted = dict(client_doc)
    if "api_creds_ref" in redacted:
        redacted["api_creds_set"] = bool(redacted["api_creds_ref"])
        redacted.pop("api_creds_ref", None)
    # Carriers sub-doc: never leak api_key_ref to the wire
    carriers = redacted.get("carriers") or {}
    if carriers:
        redacted["carriers"] = {code: _carrier_cfg_public(cfg)
                                  for code, cfg in carriers.items()}
    return redacted

