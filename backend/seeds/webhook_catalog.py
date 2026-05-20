"""Seed del catálogo de eventos webhook salientes (PROMPT 39 V3 P0.3).

5 eventos globales emitibles por toda la plataforma.
"""
from __future__ import annotations

from repositories.webhooks import WebhookEventCatalogRepository


CATALOG_V1: list[dict] = [
    {
        "event_code": "ticket.created",
        "event_name": "Ticket creado",
        "description": "Se generó un nuevo ticket de incidencia.",
        "schema_version": "v1",
        "contains_pii": True,
        "active": True,
        "payload_schema": {
            "type": "object",
            "required": ["event_id", "event_type", "occurred_at", "data"],
            "properties": {
                "event_id": {"type": "string"},
                "event_type": {"type": "string", "enum": ["ticket.created"]},
                "schema_version": {"type": "string"},
                "occurred_at": {"type": "string"},
                "data": {
                    "type": "object",
                    "properties": {
                        "ticket": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "client_id": {"type": "string"},
                                "carrier_id": {"type": ["string", "null"]},
                                "guia_id": {"type": "string"},
                                "tracking_id": {"type": ["string", "null"]},
                                "status": {"type": "string"},
                                "motivo_id": {"type": ["string", "null"]},
                                "incident_type": {"type": ["string", "null"]},
                                "destinatario": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "address_summary": {"type": "string"},
                                    },
                                },
                                "created_at": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    },
    {
        "event_code": "ticket.status_changed",
        "event_name": "Status del ticket cambió",
        "description": "El status canónico del ticket fue modificado.",
        "schema_version": "v1",
        "contains_pii": False,
        "active": True,
        "payload_schema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "properties": {
                        "ticket_id": {"type": "string"},
                        "previous_status": {"type": ["string", "null"]},
                        "new_status": {"type": "string"},
                        "actor_id": {"type": ["string", "null"]},
                        "reason": {"type": ["string", "null"]},
                    },
                },
            },
        },
    },
    {
        "event_code": "ticket.closed",
        "event_name": "Ticket cerrado",
        "description": "El ticket alcanzó un estado terminal (resolved/closed).",
        "schema_version": "v1",
        "contains_pii": False,
        "active": True,
        "payload_schema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "properties": {
                        "ticket_id": {"type": "string"},
                        "final_status": {"type": "string"},
                        "closed_by": {"type": ["string", "null"]},
                    },
                },
            },
        },
    },
    {
        "event_code": "claim.conciliated",
        "event_name": "Reclamo conciliado",
        "description": "El reclamo llegó a estado terminal `conciliado`.",
        "schema_version": "v1",
        "contains_pii": False,
        "active": True,
        "payload_schema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "string"},
                        "ticket_id": {"type": "string"},
                        "monto_aprobado": {"type": ["number", "null"]},
                        "moneda": {"type": "string"},
                    },
                },
            },
        },
    },
    {
        "event_code": "guia.delivered",
        "event_name": "Guía entregada",
        "description": "La guía alcanzó estado canónico `delivered`.",
        "schema_version": "v1",
        "contains_pii": False,
        "active": True,
        "payload_schema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "properties": {
                        "guia_id": {"type": "string"},
                        "client_id": {"type": "string"},
                        "carrier_id": {"type": ["string", "null"]},
                        "tracking_id": {"type": ["string", "null"]},
                        "delivered_at": {"type": "string"},
                    },
                },
            },
        },
    },
]


async def run() -> dict:
    """Inserta/actualiza el catálogo global. Idempotente."""
    repo = WebhookEventCatalogRepository()
    inserted = 0
    for ev in CATALOG_V1:
        await repo.upsert_global(ev)
        inserted += 1
    return {"events": inserted}
