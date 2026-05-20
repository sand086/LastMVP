"""Idempotent seed of the anchor catalog (PROMPT 07).

Inserts a global mapping (tenant_id=None) for every NATIVE_CODES entry of
the 5 anchor adapters. Tenants can override individual rows by inserting
their own (tenant_id=<id>) row in the same (carrier_id, raw_code, api_version)
slot — the normalizer prefers tenant rows.
"""
from __future__ import annotations
from datetime import datetime, timezone

from core.db import get_db
from core.logger import log
from core.uuid import new_id
from services.cae.adapters.anchor_stubs import ADAPTER_REGISTRY


async def run() -> int:
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for adapter_cls in ADAPTER_REGISTRY.values():
        carrier_id = adapter_cls.carrier_id
        api_version = adapter_cls.DEFAULT_API_VERSION
        for raw_code, meta in adapter_cls.NATIVE_CODES.items():
            canonical, incident, is_terminal, requires_action, display_label, confidence = meta
            res = await db.carrier_status_catalog.update_one(
                {
                    "carrier_id": carrier_id,
                    "raw_code": raw_code,
                    "api_version": api_version,
                    "tenant_id": None,
                },
                {
                    "$setOnInsert": {
                        "id": new_id(),
                        "tenant_id": None,
                        "carrier_id": carrier_id,
                        "raw_code": raw_code,
                        "api_version": api_version,
                        "canonical_status": canonical,
                        "incident_type": incident,
                        "is_terminal": is_terminal,
                        "requires_action": requires_action,
                        "display_label_es": display_label,
                        "confidence": confidence,
                        "active": True,
                        "source": "anchor_seed",
                        "created_at": now,
                    },
                    "$set": {"updated_at": now},
                },
                upsert=True,
            )
            if res.upserted_id is not None:
                inserted += 1
    log.info("cae_catalog_seeded", extra={"context": {"newly_inserted": inserted}})
    return inserted
