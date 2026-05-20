"""Iter55 P3.2 · Heurística para incrementar `delivery_attempts` desde eventos.

Algunos carriers no devuelven el counter explícitamente pero sí emiten eventos
del tipo "Domicilio cerrado", "Destinatario ausente", "Visita". Cada uno de
esos eventos cuenta como **1 intento**. Esta función inspecciona el
`carrier_status` del ingest actual y, si match con patrones conocidos,
incrementa el contador de la guía.

Llamada desde `IngestService.process_event` justo antes de update.

NOTA: idempotencia: si el mismo evento llega 2 veces (mismo carrier_status +
event_at), el `_dedup_key` previene doble incremento.
"""
from __future__ import annotations

from core.db import get_db
from core.logger import log


# Patrones que cuentan como "intento de entrega" (case-insensitive, substring)
ATTEMPT_PATTERNS = (
    "destinatario ausente",
    "domicilio cerrado",
    "visita",
    "intento de entrega",
    "no se localizó",
    "no se localizo",
    "se acudió al domicilio",
    "se acudio al domicilio",
)


def looks_like_attempt(carrier_status: str | None) -> bool:
    if not carrier_status:
        return False
    cs = carrier_status.lower()
    return any(p in cs for p in ATTEMPT_PATTERNS)


async def bump_attempts_if_event_indicates(
    *, tenant_id: str, guia_id: str,
    carrier_status: str, event_at: str | None,
) -> int | None:
    """Si el `carrier_status` matchea un patrón de intento, incrementa
    `delivery_attempts` y devuelve el nuevo valor. Idempotente por (guia_id,
    carrier_status, event_at) — usa colección `delivery_attempt_log`.

    Devuelve None si no aplica o ya fue procesado.
    """
    if not looks_like_attempt(carrier_status):
        return None
    db = get_db()
    dedup_key = f"{guia_id}|{carrier_status[:80]}|{event_at or ''}"
    existing = await db.delivery_attempt_log.find_one(
        {"key": dedup_key}, {"_id": 0, "key": 1},
    )
    if existing:
        return None  # ya procesado, no incrementamos
    # Atomic increment + dedup insert
    await db.delivery_attempt_log.insert_one(
        {"key": dedup_key, "tenant_id": tenant_id, "guia_id": guia_id,
         "event_at": event_at, "created_at": event_at},
    )
    from pymongo import ReturnDocument
    r = await db.guias.find_one_and_update(
        {"id": guia_id, "tenant_id": tenant_id},
        {"$inc": {"delivery_attempts": 1}},
        projection={"_id": 0, "delivery_attempts": 1},
        return_document=ReturnDocument.AFTER,
    )
    new_count = (r or {}).get("delivery_attempts", 1)
    log.info("delivery_attempt_bumped", extra={"context": {
        "tenant_id": tenant_id, "guia_id": guia_id,
        "new_count": new_count, "trigger": carrier_status[:80],
    }})
    return new_count
