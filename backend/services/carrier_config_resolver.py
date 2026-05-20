"""Carrier-config resolver — implements the SaaS inheritance hierarchy.

Resolution order (most specific wins):

  subclient.carriers.<code>          (future; not implemented yet)
        ↓
  client.carriers.<code>             (per-client override)
        ↓
  project.carriers.<code>            (future; not implemented yet)
        ↓
  tenant.carriers (collection)       (tenant has its OWN creds; ignored if it
                                      only acts as a "catalog row" without
                                      api_creds_ref)
        ↓
  platform_carrier_configs.<code>    (inherited from MyExcellence root_dev)

Returns a dict with both creds AND a `config_source` field so every consumer
(scheduler, agent cancel, admin test) can log which level resolved the call —
critical for SaaS audit & billing.
"""
from __future__ import annotations
from typing import Literal

from core.logger import log
from core.crypto import decrypt
from repositories.clients import ClientRepository
from repositories.platform_carriers import PlatformCarrierRepository


ConfigSource = Literal["client", "tenant", "platform", "none"]


async def resolve_carrier_config(
    *, tenant_id: str, client_id: str | None, code: str,
) -> dict | None:
    """Walks the hierarchy and returns the first config that has usable creds.

    Returns:
      {
        "config_source": "client" | "tenant" | "platform",
        "code": "routal",
        "api_key": "<plaintext>",
        "client_secret": "<plaintext|None>",
        "project_ids": [...],            # accumulated from cfg (may be filtered
                                          # for platform via tenant_access)
        "default_project_id": str | None,
        "base_url": str | None,
        "billing_mode": "platform_pays" | "tenant_pays_overage" | None,
        "enabled": bool,
      }
      or None if NO level has creds usable for this carrier.
    """
    code = code.lower()

    # ─── 1) per-client override (most specific) ────────────────────────
    if client_id:
        client_repo = ClientRepository(tenant_id=tenant_id)
        client_cfg = await client_repo.get_carrier_config(client_id, code)
        if client_cfg and client_cfg.get("api_key"):
            return {
                "config_source": "client",
                "code": code,
                "api_key": client_cfg["api_key"],
                "client_secret": client_cfg.get("client_secret"),
                "project_ids": client_cfg.get("project_ids") or [],
                "default_project_id": client_cfg.get("default_project_id"),
                "base_url": client_cfg.get("base_url"),
                "billing_mode": None,  # client pays its own usage
                "enabled": client_cfg.get("enabled", True),
            }

    # ─── 2) tenant-level carrier (catalog row WITH own api_creds_ref) ──
    # The existing PROMPT 11 `carriers` collection. We treat it as a config
    # SOURCE only if it has its own credentials material; otherwise it's just
    # a "this carrier is enabled on the tenant" flag and we keep descending.
    from core.db import get_db
    tenant_carrier = await get_db().carriers.find_one(
        {"tenant_id": tenant_id, "code": code}, {"_id": 0})
    if tenant_carrier and tenant_carrier.get("api_creds_ref"):
        try:
            api_key = decrypt(tenant_carrier["api_creds_ref"])
        except ValueError:
            api_key = None
        if api_key:
            return {
                "config_source": "tenant",
                "code": code,
                "api_key": api_key,
                "client_secret": None,
                "project_ids": [],
                "default_project_id": None,
                "base_url": tenant_carrier.get("api_url"),
                "billing_mode": None,
                "enabled": tenant_carrier.get("status", "active") == "active",
            }

    # ─── 3) platform inherits (root_dev) ───────────────────────────────
    platform_repo = PlatformCarrierRepository()
    plat = await platform_repo.get_decrypted(code)
    if plat and plat.get("api_key"):
        # Whitelist enforcement: if tenant_access is non-empty, the tenant
        # must appear in it AND its entry must be enabled.
        access_map = plat.get("tenant_access") or {}
        if access_map:  # whitelist mode
            tenant_entry = access_map.get(tenant_id)
            if not tenant_entry or tenant_entry.get("enabled") is False:
                log.info("platform_carrier_access_denied", extra={"context": {
                    "tenant_id": tenant_id, "code": code,
                }})
                return None
            allowed_project_ids = tenant_entry.get("project_ids") or []
        else:
            # Open access — every tenant inherits. Reasonable default for
            # carriers without project segmentation (DHL/FedEx).
            allowed_project_ids = []
        return {
            "config_source": "platform",
            "code": code,
            "api_key": plat["api_key"],
            "client_secret": plat.get("client_secret"),
            "project_ids": allowed_project_ids,
            "default_project_id": allowed_project_ids[0] if allowed_project_ids else None,
            "base_url": plat.get("base_url"),
            "billing_mode": plat.get("billing_mode"),
            "enabled": True,
        }

    return None
