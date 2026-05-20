"""Seed inicial del catálogo de IA (PROMPT 26).

Idempotente: corre en cada boot, sólo inserta si no existe.

Features default (3):
  - classify_motivo       Haiku · agent_internal
  - summarize_timeline    Sonnet · agent_internal
  - draft_response_to_client  Sonnet · client_final (R42 → draft=true)

Brackets default (4):
  - starter   $29/mes · 100 invocaciones · cap $5
  - growth    $99/mes · 1000 invocaciones · cap $50
  - scale     $299/mes · 5000 invocaciones · cap $200
  - enterprise $999/mes · 25000 invocaciones · cap $1000
"""
from __future__ import annotations
from datetime import datetime, timezone

from core.db import get_db
from core.logger import log
from core.uuid import new_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


SEED_FEATURES = [
    {
        "feature_code": "classify_motivo",
        "feature_name": "Clasificación de motivo",
        "description": "Sugiere el motivo de incidencia a partir de la descripción libre.",
        "recommended_model": "claude-haiku-4-5-20251001",
        "recommended_provider": "anthropic",
        "avg_input_tokens": 400,
        "avg_output_tokens": 30,
        "avg_cost_usd": 0.001,
        "destinatario": "agent_internal",
        "cache_enabled": True,
        "active": True,
    },
    {
        "feature_code": "summarize_timeline",
        "feature_name": "Resumen de timeline",
        "description": "Resume el timeline de un ticket en máximo 4 líneas operativas.",
        "recommended_model": "claude-sonnet-4-5-20250929",
        "recommended_provider": "anthropic",
        "avg_input_tokens": 1200,
        "avg_output_tokens": 200,
        "avg_cost_usd": 0.0066,
        "destinatario": "agent_internal",
        "cache_enabled": False,
        "active": True,
    },
    {
        "feature_code": "draft_response_to_client",
        "feature_name": "Borrador de respuesta al cliente",
        "description": "Redacta un draft empático para enviar al cliente final (R42 → draft=true).",
        "recommended_model": "claude-sonnet-4-5-20250929",
        "recommended_provider": "anthropic",
        "avg_input_tokens": 1500,
        "avg_output_tokens": 300,
        "avg_cost_usd": 0.0090,
        "destinatario": "client_final",
        "cache_enabled": False,
        "active": True,
    },
]

SEED_BRACKETS = [
    {
        "bracket_name": "starter",
        "included_invocations_per_month": 100,
        "included_tokens_per_month": 100_000,
        "overage_per_1k_tokens_usd": 0.02,
        "hard_cap_usd_per_month": 5.0,
        "alert_threshold_pct": 80,
        "monthly_fee_usd": 29.0,
        "active": True,
    },
    {
        "bracket_name": "growth",
        "included_invocations_per_month": 1000,
        "included_tokens_per_month": 1_000_000,
        "overage_per_1k_tokens_usd": 0.015,
        "hard_cap_usd_per_month": 50.0,
        "alert_threshold_pct": 80,
        "monthly_fee_usd": 99.0,
        "active": True,
    },
    {
        "bracket_name": "scale",
        "included_invocations_per_month": 5000,
        "included_tokens_per_month": 5_000_000,
        "overage_per_1k_tokens_usd": 0.012,
        "hard_cap_usd_per_month": 200.0,
        "alert_threshold_pct": 80,
        "monthly_fee_usd": 299.0,
        "active": True,
    },
    {
        "bracket_name": "enterprise",
        "included_invocations_per_month": 25000,
        "included_tokens_per_month": 25_000_000,
        "overage_per_1k_tokens_usd": 0.008,
        "hard_cap_usd_per_month": 1000.0,
        "alert_threshold_pct": 80,
        "monthly_fee_usd": 999.0,
        "active": True,
    },
]


async def run() -> None:
    db = get_db()

    # Features (tenant_id=None → globales)
    inserted_f = 0
    migrated_f = 0
    for f in SEED_FEATURES:
        existing = await db.ai_features.find_one({"feature_code": f["feature_code"]})
        if existing:
            # Migración suave: aplicar campos NUEVOS que aún no estén en el doc.
            # No sobrescribimos cambios manuales del admin (PATCH), sólo agregamos.
            missing = {k: v for k, v in f.items() if k not in existing}
            if missing:
                missing["updated_at"] = _now()
                await db.ai_features.update_one(
                    {"feature_code": f["feature_code"]}, {"$set": missing},
                )
                migrated_f += 1
            continue
        await db.ai_features.insert_one({
            "id": new_id(), "tenant_id": None,
            **f, "created_at": _now(), "updated_at": _now(),
        })
        inserted_f += 1

    # Brackets (globales)
    inserted_b = 0
    for b in SEED_BRACKETS:
        if await db.ai_pricing_brackets.find_one({"bracket_name": b["bracket_name"]}):
            continue
        await db.ai_pricing_brackets.insert_one({
            "id": new_id(), **b, "created_at": _now(),
        })
        inserted_b += 1

    if inserted_f or inserted_b or migrated_f:
        log.info("ai_catalog_seeded", extra={"context": {
            "features_inserted": inserted_f,
            "features_migrated": migrated_f,
            "brackets_inserted": inserted_b,
        }})
