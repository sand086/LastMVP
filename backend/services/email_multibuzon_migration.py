"""Bundle G · Migración backward-compatible mono-buzón → multi-buzón.

Para cada tenant que tenga `tenant_email_settings` con `status='active'` y
`api_key_ref`, crea:
  1) 1 fila en email_domains (domain extraído de sender_email, verified=True).
  2) 1 fila en email_mailboxes (is_default_for_tenant=True, hereda credenciales).
  3) 1 fila en email_routing (workflow_type='generic', priority=100).

Marca el doc legacy con `migrated_to_multibuzon=True` y `migrated_at`. NO
borra el doc original — la limpieza se hace en una migración posterior
después de 30 días sin incidentes.

Idempotente: si ya hay buzones para el tenant, NO duplica.
"""
from __future__ import annotations
from datetime import datetime, timezone

from core.db import get_db
from core.logger import log
from repositories.email_multibuzon import (
    make_domain_doc, make_mailbox_doc, make_routing_doc,
)


async def migrate_tenant(tenant_id: str) -> dict:
    """Migra UN tenant. Devuelve dict con info de qué se hizo.

    Estados posibles:
      - 'skipped_no_legacy'      : no había `tenant_email_settings`.
      - 'skipped_inactive'       : legacy existe pero status != active.
      - 'skipped_already_done'   : el tenant ya tiene >=1 mailbox.
      - 'migrated'               : se creó domain+mailbox+routing.
    """
    db = get_db()
    # ¿Ya tiene mailboxes? → idempotente
    existing = await db.email_mailboxes.count_documents({"tenant_id": tenant_id})
    if existing > 0:
        return {"status": "skipped_already_done", "tenant_id": tenant_id}

    legacy = await db.tenant_email_settings.find_one(
        {"tenant_id": tenant_id}, {"_id": 0},
    )
    if not legacy:
        return {"status": "skipped_no_legacy", "tenant_id": tenant_id}
    if legacy.get("status") != "active" or not legacy.get("api_key_ref"):
        return {"status": "skipped_inactive", "tenant_id": tenant_id}

    sender_email = (legacy.get("sender_email") or "").lower()
    if "@" not in sender_email:
        return {"status": "skipped_bad_email", "tenant_id": tenant_id,
                "sender_email": sender_email}
    domain_name = sender_email.split("@", 1)[1]
    created_by = legacy.get("updated_by") or "system_migration"

    # 1) Domain (verified=True por backward-compat; cron lo re-validará en 24h)
    domain_doc = make_domain_doc(
        tenant_id=tenant_id, domain=domain_name, created_by=created_by,
        verification_status="verified", dkim=True, spf=True, dmarc=True,
    )
    await db.email_domains.insert_one(domain_doc)

    # 2) Mailbox — reusa el api_key_ref encriptado tal cual del legacy
    now = datetime.now(timezone.utc).isoformat()
    mailbox_doc = {
        "id": _new_id(),
        "tenant_id": tenant_id,
        "client_id": None,
        "domain_id": domain_doc["id"],
        "display_name": "Buzón principal (migrado)",
        "sender_name": legacy.get("sender_name", "MyExcellence"),
        "sender_email": sender_email,
        "reply_to_email": (legacy.get("reply_to_default") or "").lower() or None,
        "is_active": True,
        "is_default_for_tenant": True,
        "is_default_for_client": False,
        "daily_send_limit": None,
        "monthly_send_count": 0,
        "workflow_types": ["generic", "ticket_notification",
                            "claim_communication", "sla_alert",
                            "admin_notification"],
        "api_key_ref": legacy["api_key_ref"],  # reusa el cipher legacy
        "api_key_last4": legacy.get("api_key_last4", ""),
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }
    await db.email_mailboxes.insert_one(mailbox_doc)

    # 3) Routing generic (catch-all default del tenant)
    routing_doc = make_routing_doc(
        tenant_id=tenant_id, mailbox_id=mailbox_doc["id"],
        workflow_type="generic", priority=100,
        description="Migrado desde modelo mono-buzón",
    )
    await db.email_routing.insert_one(routing_doc)

    # 4) Marcar legacy como migrado (NO borrar)
    await db.tenant_email_settings.update_one(
        {"tenant_id": tenant_id},
        {"$set": {
            "migrated_to_multibuzon": True,
            "migrated_at": now,
            "migrated_domain_id": domain_doc["id"],
            "migrated_mailbox_id": mailbox_doc["id"],
        }},
    )
    log.info("email_multibuzon_migrated", extra={"context": {
        "tenant_id": tenant_id, "domain": domain_name,
        "mailbox_id": mailbox_doc["id"],
    }})
    return {
        "status": "migrated", "tenant_id": tenant_id,
        "domain_id": domain_doc["id"], "mailbox_id": mailbox_doc["id"],
        "routing_id": routing_doc["id"],
    }


async def migrate_all_tenants() -> dict:
    """Recorre todos los tenants con legacy config. Útil para script CLI."""
    db = get_db()
    cursor = db.tenant_email_settings.find(
        {"status": "active"}, {"_id": 0, "tenant_id": 1},
    )
    results = {"migrated": 0, "skipped": 0, "details": []}
    async for row in cursor:
        r = await migrate_tenant(row["tenant_id"])
        results["details"].append(r)
        if r["status"] == "migrated":
            results["migrated"] += 1
        else:
            results["skipped"] += 1
    return results


def _new_id() -> str:
    from core.uuid import new_id
    return new_id()
