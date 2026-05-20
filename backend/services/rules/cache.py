"""Cache adapter para projecciones de reglas — Bundle B · R50.

Usamos una colección Mongo con índice TTL (no Redis para mantener nuestro
stack mínimo). Cada documento expira automáticamente a los `expires_at`.

Estructura:
    {
      "id": "tenant_id:ticket_id:user_role_hash",   # _id semántico
      "tenant_id": "...",
      "scope": "ticket" | "reclamo",
      "entity_id": "...",
      "user_role": "agent" | "admin" | ...,
      "payload": {...},                              # TicketProjection serializada
      "computed_at": "...",
      "expires_at": ISO,                             # Mongo TTL borra automático
    }

Invalidación explícita:
- `invalidate_tickets_for_motivo(motivo_id)` cuando se modifica un motivo.
- `invalidate_tickets_for_client(client_id)` cuando se modifica la matriz.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.db import get_db

COLLECTION_NAME = "rule_projection_cache"
# Reusable TTL — al insertar un doc, fijamos expires_at; Mongo borra al expirar.
_INDEX_CREATED = False


async def _ensure_index() -> None:
    global _INDEX_CREATED
    if _INDEX_CREATED:
        return
    db = get_db()
    await db[COLLECTION_NAME].create_index(
        "expires_at", expireAfterSeconds=0,
    )
    await db[COLLECTION_NAME].create_index(
        [("tenant_id", 1), ("scope", 1), ("entity_id", 1)],
    )
    _INDEX_CREATED = True


def _cache_key(*, tenant_id: str, scope: str, entity_id: str, user_role: str) -> str:
    return f"{tenant_id}:{scope}:{entity_id}:{user_role}"


async def get(
    *, tenant_id: str, scope: str, entity_id: str, user_role: str,
) -> Optional[dict]:
    """Devuelve la proyección cacheada o None si falta / expiró."""
    await _ensure_index()
    db = get_db()
    return await db[COLLECTION_NAME].find_one(
        {"id": _cache_key(tenant_id=tenant_id, scope=scope,
                          entity_id=entity_id, user_role=user_role)},
        {"_id": 0, "payload": 1, "computed_at": 1},
    )


async def put(
    *, tenant_id: str, scope: str, entity_id: str, user_role: str,
    payload: dict, ttl_seconds: int,
) -> None:
    """Persiste payload con expiración por TTL. Idempotente (upsert)."""
    await _ensure_index()
    now = datetime.now(timezone.utc)
    db = get_db()
    await db[COLLECTION_NAME].update_one(
        {"id": _cache_key(tenant_id=tenant_id, scope=scope,
                          entity_id=entity_id, user_role=user_role)},
        {"$set": {
            "tenant_id": tenant_id,
            "scope": scope,
            "entity_id": entity_id,
            "user_role": user_role,
            "payload": payload,
            "computed_at": now.isoformat(),
            "expires_at": now + timedelta(seconds=ttl_seconds),
        }},
        upsert=True,
    )


async def invalidate_entity(
    *, tenant_id: str, scope: str, entity_id: str,
) -> None:
    """Borra todas las proyecciones cacheadas de una entidad
    (cualquier user_role)."""
    db = get_db()
    await db[COLLECTION_NAME].delete_many({
        "tenant_id": tenant_id, "scope": scope, "entity_id": entity_id,
    })


async def invalidate_tickets_for_motivo(*, tenant_id: str, motivo_id: str) -> None:
    """Borra cache de todos los tickets con ese motivo (admin cambió R03)."""
    db = get_db()
    ticket_ids = await db.tickets.distinct(
        "id", {"tenant_id": tenant_id, "motivo_id": motivo_id},
    )
    if not ticket_ids:
        return
    await db[COLLECTION_NAME].delete_many({
        "tenant_id": tenant_id, "scope": "ticket",
        "entity_id": {"$in": ticket_ids},
    })


async def invalidate_tickets_for_client(*, tenant_id: str, client_id: str) -> None:
    """Borra cache de todos los tickets del cliente (matriz R03 cambió)."""
    db = get_db()
    ticket_ids = await db.tickets.distinct(
        "id", {"tenant_id": tenant_id, "client_id": client_id},
    )
    if not ticket_ids:
        return
    await db[COLLECTION_NAME].delete_many({
        "tenant_id": tenant_id, "scope": "ticket",
        "entity_id": {"$in": ticket_ids},
    })
