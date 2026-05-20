"""Demo claims seed — provisions 3 sample reclamos en distintos estados.

Used by the admin-only endpoint `POST /api/admin/seed/demo-claims` so QA y demos
puedan validar visualmente los flujos PDF/ZIP, bulk operations y kanban.

Idempotente: marca cada ticket+claim con ``seed_marker="demo_claim_v1"`` y
no re-crea si ya existen.

Estados generados:
  1. expediente_en_armado   — para probar bulk-status-change
  2. en_dictamen_carrier    — para probar PDF de un reclamo en mid-flow
  3. conciliado             — terminal, ZIP bulk export
"""
from __future__ import annotations
from datetime import datetime, timezone

from core.db import get_db
from core.logger import log
from core.uuid import new_id


SEED_MARKER = "demo_claim_v1"

_SEEDS = [
    {
        "estado": "expediente_en_armado",
        "tipo_dano": "dano_total",
        "monto_reclamado": 12500.00,
        "declaracion": "El paquete llegó con la caja completamente aplastada.",
    },
    {
        "estado": "en_dictamen_carrier",
        "tipo_dano": "extravio",
        "monto_reclamado": 3499.50,
        "declaracion": "Se reporta paquete extraviado tras 14 días sin movimientos.",
    },
    {
        "estado": "conciliado",
        "tipo_dano": "dano_parcial",
        "monto_reclamado": 875.00,
        "monto_conciliado": 750.00,
        "declaracion": "Daño superficial en empaque, contenido en buen estado.",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ensure_client(db, tenant_id: str) -> str:
    existing = await db.clients.find_one(
        {"tenant_id": tenant_id, "name": "Demo Cliente Reclamos"},
        {"_id": 0, "id": 1},
    )
    if existing:
        return existing["id"]
    cid = new_id()
    await db.clients.insert_one({
        "id": cid, "tenant_id": tenant_id,
        "name": "Demo Cliente Reclamos",
        "slug": "demo-cliente-reclamos",
        "status": "active",
        "automation_enabled": False,
        "ingest_mode": "manual",
        "created_at": _now(),
    })
    return cid


async def _create_ticket(db, *, tenant_id: str, client_id: str,
                          tracking_id: str, idx: int) -> str:
    tid = new_id()
    await db.tickets.insert_one({
        "id": tid, "tenant_id": tenant_id, "client_id": client_id,
        "tracking_id": tracking_id,
        "status": "closed", "is_terminal": True,
        "incident_type": "damaged",
        "motivo_codigo": "DAMAGED",
        "seed_marker": SEED_MARKER,
        "created_at": _now(), "updated_at": _now(),
        "closed_at": _now(),
    })
    # Evento append-only mínimo
    await db.ticket_events.insert_one({
        "id": new_id(), "tenant_id": tenant_id, "ticket_id": tid,
        "event_type": "demo_seed",
        "payload": {"seed_marker": SEED_MARKER, "idx": idx},
        "description": "Ticket creado por seed demo",
        "created_at": _now(),
    })
    return tid


async def _create_claim(db, *, tenant_id: str, ticket_id: str, client_id: str,
                          spec: dict) -> str:
    cid = new_id()
    estado = spec["estado"]
    is_terminal = estado in ("conciliado", "desistido")
    doc = {
        "id": cid, "tenant_id": tenant_id,
        "ticket_id": ticket_id, "client_id": client_id,
        "estado": estado, "is_terminal": is_terminal,
        "tipo_dano": spec["tipo_dano"],
        "monto_reclamado": spec["monto_reclamado"],
        "divisa": "MXN",
        "promoted_by": "seed",
        "promoted_at": _now(),
        "expediente": {
            "declaracion_cliente": spec["declaracion"],
            "evidencia_ids": [],
        },
        "seed_marker": SEED_MARKER,
        "created_at": _now(), "updated_at": _now(),
    }
    if is_terminal:
        doc["conciliado_at"] = _now()
        doc["conciliado_por"] = "seed"
    await db.claims.insert_one(doc)
    # Eventos append-only
    await db.claim_events.insert_one({
        "id": new_id(), "tenant_id": tenant_id, "claim_id": cid,
        "event_type": "claim_promoted",
        "estado_anterior": None, "estado_nuevo": "promovido",
        "payload": {"seed": True}, "created_at": _now(),
    })
    if estado != "promovido":
        await db.claim_events.insert_one({
            "id": new_id(), "tenant_id": tenant_id, "claim_id": cid,
            "event_type": "claim_transitioned",
            "estado_anterior": "promovido", "estado_nuevo": estado,
            "payload": {"seed": True}, "created_at": _now(),
        })
    # Indemnización para estado terminal con monto conciliado
    if estado == "conciliado":
        await db.indemnizations.insert_one({
            "id": new_id(), "tenant_id": tenant_id, "claim_id": cid,
            "monto_aprobado": spec["monto_conciliado"],
            "divisa": "MXN",
            "carrier_referencia": f"DEMO-REF-{cid[:8]}",
            "monto_conciliado": spec["monto_conciliado"],
            "divisa_conciliado": "MXN",
            "conciliado_at": _now(),
            "created_at": _now(),
        })
    return cid


async def seed_demo_claims(*, tenant_slug: str = "myexcellence") -> dict:
    """Crea 3 reclamos demo en el tenant indicado. Idempotente."""
    db = get_db()
    tenant = await db.tenants.find_one({"slug": tenant_slug}, {"_id": 0, "id": 1})
    if not tenant:
        return {"created": 0, "skipped": 0, "reason": "tenant_not_found"}

    tenant_id = tenant["id"]
    # Idempotencia: si ya hay reclamos con seed_marker, skip
    existing = await db.claims.count_documents(
        {"tenant_id": tenant_id, "seed_marker": SEED_MARKER},
    )
    if existing >= len(_SEEDS):
        log.info("demo_claims_already_seeded",
                  extra={"context": {"tenant_id": tenant_id, "count": existing}})
        return {"created": 0, "skipped": existing,
                "reason": "already_seeded", "tenant_id": tenant_id}

    client_id = await _ensure_client(db, tenant_id)
    created_ids: list[str] = []
    for i, spec in enumerate(_SEEDS):
        tracking = f"DEMO-{SEED_MARKER}-{i+1:02d}"
        ticket_id = await _create_ticket(
            db, tenant_id=tenant_id, client_id=client_id,
            tracking_id=tracking, idx=i,
        )
        claim_id = await _create_claim(
            db, tenant_id=tenant_id, ticket_id=ticket_id,
            client_id=client_id, spec=spec,
        )
        created_ids.append(claim_id)

    log.info("demo_claims_seeded",
              extra={"context": {"tenant_id": tenant_id, "count": len(created_ids)}})
    return {"created": len(created_ids), "skipped": 0,
            "claim_ids": created_ids, "tenant_id": tenant_id}
