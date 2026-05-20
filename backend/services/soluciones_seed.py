"""Iter54 — Seed de soluciones derivadas del documento del cliente.

Seedea **soluciones** estándar mapeadas a los flujos del documento
"Tipos de incidencia y soluciones".  Reutiliza los `motivos` existentes
del tenant; si no existe el motivo, se crea on-the-fly por `(tenant_id,
incident_type)` con un nombre legible.

Por incidente, se siembran las siguientes soluciones:
  - address_issue:
      * `address_issue_contact_recipient`      (canal: email)
      * `address_issue_request_info`           (canal: email)
  - refused:
      * `refused_acknowledge`                  (canal: email)
      * `refused_request_instructions`         (canal: email)
  - recipient_absent:
      * `absent_contact_recipient`             (canal: email)
      * `absent_unresponsive_warning`          (canal: email)
  - común:
      * `auto_return_to_origin`                (canal: api — stub)

Idempotente: usa `slug` único por solución.
"""
from __future__ import annotations
from datetime import datetime, timezone

from core.db import get_db
from core.uuid import new_id


# (slug, name, incident_type, automatable, channel_hint, template_email)
SEED_SOLUCIONES: list[tuple[str, str, str, bool, str, str]] = [
    (
        "address_issue_contact_recipient",
        "Contactar al destinatario para validar dirección",
        "address_issue", True, "email",
        "Validar información de entrega y solicitar referencias adicionales.",
    ),
    (
        "address_issue_request_info",
        "Solicitar al cliente referencias del domicilio",
        "address_issue", True, "email",
        "Pedir al responsable un número alterno o referencias visuales.",
    ),
    (
        "refused_acknowledge",
        "Notificar rechazo confirmado por el destinatario",
        "refused", True, "email",
        "Comunicar al responsable el motivo del rechazo y solicitar instrucciones.",
    ),
    (
        "refused_request_instructions",
        "Solicitar instrucciones al cliente tras rechazo",
        "refused", True, "email",
        "Esperar decisión del cliente: re-entrega o devolución.",
    ),
    (
        "absent_contact_recipient",
        "Contactar al destinatario por ausencia",
        "recipient_absent", True, "email",
        "Coordinar un nuevo intento de entrega para 24-48hs hábiles.",
    ),
    (
        "absent_unresponsive_warning",
        "Aviso al cliente de falta de respuesta",
        "recipient_absent", True, "email",
        "Tercer aviso. Próximo paso: retorno a origen automático.",
    ),
    (
        "auto_return_to_origin",
        "Retorno automático a origen",
        "exception", False, "api",  # api por ahora no automatable
        "Solicitar al carrier que retorne el paquete a origen.",
    ),
]


async def _resolve_or_create_motivo(*, tenant_id: str,
                                     incident_type: str) -> str:
    """Devuelve `motivo.id` para el incident_type. Crea uno default si falta."""
    db = get_db()
    existing = await db.motivos.find_one(
        {"tenant_id": tenant_id, "code": incident_type}, {"_id": 0, "id": 1},
    )
    if existing:
        return existing["id"]
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": new_id(), "tenant_id": tenant_id,
        "code": incident_type,
        "name": _MOTIVO_NAMES.get(incident_type, incident_type.title()),
        "description": "Auto-seed (iter54)",
        "active": True,
        "created_at": now, "updated_at": now,
    }
    await db.motivos.insert_one(doc)
    return doc["id"]


_MOTIVO_NAMES: dict[str, str] = {
    "address_issue":    "Problema de dirección",
    "refused":          "Rechazo del destinatario",
    "recipient_absent": "Destinatario ausente",
    "exception":        "Incidencia genérica",
}


async def seed_soluciones(*, tenant_id: str) -> dict:
    """Idempotente. Crea/actualiza soluciones por `(tenant_id, slug)`."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    updated = 0
    for (slug, name, incident_type, automatable, channel_hint, template) in SEED_SOLUCIONES:
        motivo_id = await _resolve_or_create_motivo(
            tenant_id=tenant_id, incident_type=incident_type)
        q = {"tenant_id": tenant_id, "slug": slug}
        existing = await db.soluciones.find_one(q, {"_id": 0, "id": 1, "created_at": 1})
        doc = {
            "tenant_id": tenant_id, "slug": slug,
            "motivo_id": motivo_id,
            "name": name,
            "incident_type": incident_type,
            "automatable": automatable,
            "channel_hint": channel_hint,
            "template_email": template,
            "steps": [],
            "active": True,
            "updated_at": now,
        }
        if existing:
            doc["id"] = existing["id"]
            doc["created_at"] = existing.get("created_at", now)
            await db.soluciones.update_one(
                {"id": existing["id"]}, {"$set": doc})
            updated += 1
        else:
            doc["id"] = new_id()
            doc["created_at"] = now
            await db.soluciones.insert_one(doc)
            inserted += 1
    return {"inserted": inserted, "updated": updated, "total": len(SEED_SOLUCIONES)}
