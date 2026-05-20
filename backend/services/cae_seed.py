"""Iter54 — Seed default CAE catalog para los 4 carriers principales.

Cubre los strings frecuentes que llegan en Layout V2 CSV (en español) además
de los códigos nativos del API. Sin esto el `StatusNormalizer` devuelve
`canonical_status="unknown"` y obliga al fallback de iter52.

Carriers cubiertos: fedex, dhl, redpack, estafeta.
Cobertura por carrier:
  - Entregado          → delivered    (terminal)
  - En tránsito        → in_transit
  - Recolectado        → in_transit
  - En reparto         → in_transit
  - Domicilio cerrado  → exception/recipient_absent
  - Destinatario ausente → exception/recipient_absent
  - Visita             → exception/recipient_absent  (Redpack)
  - Rechazado          → exception/refused
  - Dirección incorrecta → exception/address_issue
  - Devuelto a origen  → returned     (terminal)

Idempotente: `upsert` por (tenant, carrier_id, raw_code, api_version).
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Iterable

from core.db import get_db
from core.uuid import new_id


# Estructura: lista de tuples (carrier_id, raw_code_es, canonical, incident_type,
#                              is_terminal, requires_action, display_label_es)
SEED_ENTRIES: list[tuple[str, str, str, str | None, bool, bool, str]] = []


def _add_for_carrier(carrier_id: str) -> None:
    SEED_ENTRIES.extend([
        # Terminal positivos
        (carrier_id, "Entregado",          "delivered",  None,                True,  False, "Entregado"),
        (carrier_id, "ENTREGADO",          "delivered",  None,                True,  False, "Entregado"),
        # En tránsito
        (carrier_id, "En tránsito",        "in_transit", None,                False, False, "En tránsito"),
        (carrier_id, "En transito",        "in_transit", None,                False, False, "En tránsito"),
        (carrier_id, "Recolectado",        "in_transit", None,                False, False, "Recolectado"),
        (carrier_id, "En reparto",         "in_transit", None,                False, False, "En reparto"),
        # Incidencias — Destinatario ausente / Domicilio cerrado
        (carrier_id, "Destinatario ausente", "exception", "recipient_absent", False, True,  "Destinatario ausente"),
        (carrier_id, "Domicilio cerrado",    "exception", "recipient_absent", False, True,  "Domicilio cerrado al momento de la visita"),
        # Rechazo
        (carrier_id, "Rechazado",          "exception",  "refused",           False, True,  "Rechazado por el destinatario"),
        (carrier_id, "Rechazo",            "exception",  "refused",           False, True,  "Rechazo"),
        # Dirección
        (carrier_id, "Dirección incorrecta", "exception", "address_issue",    False, True,  "Dirección incorrecta"),
        (carrier_id, "Dirección insuficiente", "exception", "address_issue",  False, True,  "Dirección insuficiente"),
        # Returned terminal
        (carrier_id, "Devuelto a origen",  "returned",   "returned",          True,  False, "Devuelto a origen"),
    ])


_add_for_carrier("fedex")
_add_for_carrier("dhl")
_add_for_carrier("redpack")
_add_for_carrier("estafeta")

# Iter58 — Routal (planner / lastmile). Cubbo y otros tenants usan estos códigos.
SEED_ENTRIES.extend([
    # raw_code nativo del API (lower) — el adapter lower-casea antes de pasar.
    ("routal", "pending",    "in_transit", None,                False, False, "Pendiente / en camino"),
    ("routal", "incomplete", "exception",  "failed",            False, True,  "Entrega incompleta"),
    ("routal", "completed",  "delivered",  None,                True,  False, "Entregado"),
    # Cancelado: terminal pero NO delivered. Se trata como returned + incident=failed
    # para que el WorkflowEngine cree ticket de seguimiento.
    ("routal", "canceled",   "returned",   "failed",            True,  True,  "Cancelado"),
    # carrier_status (description ES) — fallback cuando llega texto descriptivo.
    ("routal", "Cancelado",            "returned",   "failed",         True,  True,  "Cancelado"),
    ("routal", "Entrega incompleta",   "exception",  "failed",         False, True,  "Entrega incompleta"),
    ("routal", "Entregado",            "delivered",  None,             True,  False, "Entregado"),
    ("routal", "Pendiente / en camino", "in_transit", None,            False, False, "Pendiente / en camino"),
])

# Redpack-specific (terminología del documento del cliente)
SEED_ENTRIES.append(
    ("redpack", "Visita", "exception", "recipient_absent", False, True,
     "Visita - destinatario ausente"),
)


async def seed_cae_defaults(*, tenant_id: str | None = None,
                             scope: str = "tenant") -> dict:
    """Upserta los entries default. Idempotente.

    - `tenant_id`: si es None y scope="global", crea entries globales (visibles
      para todos los tenants en lookup). Si scope="tenant" requiere tenant_id.
    - Retorna `{inserted, updated, total}`.
    """
    if scope == "tenant" and not tenant_id:
        raise ValueError("scope='tenant' requires tenant_id")

    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    updated = 0
    for (carrier_id, raw_code, canonical, incident_type,
         is_terminal, requires_action, label_es) in SEED_ENTRIES:
        q = {
            "carrier_id": carrier_id,
            "raw_code": raw_code,
            "api_version": "v1",
            "scope": scope,
        }
        if scope == "tenant":
            q["tenant_id"] = tenant_id
        existing = await db.carrier_status_catalog.find_one(q, {"_id": 0, "id": 1})
        doc = {
            **q,
            "canonical_status": canonical,
            "incident_type": incident_type,
            "is_terminal": is_terminal,
            "requires_action": requires_action,
            "display_label_es": label_es,
            "confidence": 95,
            "active": True,
            "updated_at": now,
        }
        if existing:
            await db.carrier_status_catalog.update_one(
                {"id": existing["id"]}, {"$set": doc})
            updated += 1
        else:
            doc["id"] = new_id()
            doc["created_at"] = now
            await db.carrier_status_catalog.insert_one(doc)
            inserted += 1
    return {"inserted": inserted, "updated": updated, "total": len(SEED_ENTRIES)}


def iter_seed_entries() -> Iterable[tuple]:
    """Expuesto para tests."""
    return iter(SEED_ENTRIES)
