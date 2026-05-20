"""Bundle G · Email Multi-Buzón — repositorios para las 4 colecciones nuevas.

Adaptación a MongoDB del schema MariaDB del prompt original:
  - email_domains
  - email_mailboxes
  - email_routing
  - email_send_log  (append-only análogo a R04 / timeline_events)

Todos los repositorios heredan de BaseRepository → scope automático por
tenant_id (R01) y proyección que excluye _id.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from .base import BaseRepository
from core.uuid import new_id
from core.crypto import encrypt


# ─────────────────────────────────────────────────────────────
class EmailDomainRepository(BaseRepository):
    collection_name = "email_domains"


class EmailMailboxRepository(BaseRepository):
    collection_name = "email_mailboxes"

    async def find_default_for_client(self, client_id: str) -> Optional[dict]:
        return await self.find_one({
            "client_id": client_id,
            "is_default_for_client": True,
            "is_active": True,
        })

    async def find_default_for_tenant(self) -> Optional[dict]:
        return await self.find_one({
            "client_id": None,
            "is_default_for_tenant": True,
            "is_active": True,
        })

    async def clear_default_flag(self, *, scope: str, client_id: Optional[str] = None,
                                  exclude_id: Optional[str] = None) -> None:
        """``scope`` = 'tenant' o 'client'. Limpia el flag default para que solo
        un buzón quede como default a la vez (constraint emulado en app)."""
        field = "is_default_for_tenant" if scope == "tenant" else "is_default_for_client"
        q = self._scope({field: True})
        if scope == "client":
            q["client_id"] = client_id
        if exclude_id:
            q["id"] = {"$ne": exclude_id}
        await self.col.update_many(q, {"$set": {field: False}})


class EmailRoutingRepository(BaseRepository):
    collection_name = "email_routing"

    async def find_matching(self, *, workflow_type: str,
                             client_id: Optional[str],
                             motivo_id: Optional[str]) -> list[dict]:
        """Devuelve reglas que coinciden con el contexto, ordenadas por
        especificidad descendiente y priority descendiente."""
        # Match: workflow_type es obligatorio; client_id/motivo_id pueden ser
        # NULL (regla genérica) o coincidir exacto.
        q = self._scope({"workflow_type": workflow_type, "active": True})
        q["$and"] = [
            {"$or": [{"client_id": None}, {"client_id": client_id}]},
            {"$or": [{"motivo_id": None}, {"motivo_id": motivo_id}]},
        ]
        rows = await self.col.find(q, {"_id": 0}).to_list(length=100)
        # Especificidad: cuántos campos non-null tiene la regla (más = más específica)
        def _spec(r):
            return ((1 if r.get("client_id") else 0)
                    + (1 if r.get("motivo_id") else 0))
        rows.sort(key=lambda r: (_spec(r), r.get("priority", 100)), reverse=True)
        return rows


class EmailSendLogRepository(BaseRepository):
    """Append-only (R04). Solo update permitido: status, delivered_at,
    error_code, error_message vía webhook del proveedor."""
    collection_name = "email_send_log"


# ─────────────────────────────────────────────────────────────
# Helpers para crear documentos consistentes
# ─────────────────────────────────────────────────────────────
def make_domain_doc(*, tenant_id: str, domain: str, created_by: str,
                    provider: str = "resend",
                    verification_status: str = "pending",
                    dkim: bool = False, spf: bool = False, dmarc: bool = False,
                    dns_records: Optional[list] = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": new_id(),
        "tenant_id": tenant_id,
        "domain": domain.lower(),
        "provider": provider,
        "provider_domain_id": None,
        "verification_status": verification_status,
        "dkim_verified": dkim,
        "spf_verified": spf,
        "dmarc_verified": dmarc,
        "verified_at": now if verification_status == "verified" else None,
        "last_check_at": None,
        "dns_records": dns_records or [],
        "degraded": False,
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }


def make_mailbox_doc(*, tenant_id: str, domain_id: str, created_by: str,
                     display_name: str, sender_name: str, sender_email: str,
                     reply_to_email: Optional[str] = None,
                     client_id: Optional[str] = None,
                     api_key: Optional[str] = None,
                     daily_send_limit: Optional[int] = None,
                     is_default_for_tenant: bool = False,
                     is_default_for_client: bool = False,
                     workflow_types: Optional[list] = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": new_id(),
        "tenant_id": tenant_id,
        "client_id": client_id,
        "domain_id": domain_id,
        "display_name": display_name,
        "sender_name": sender_name,
        "sender_email": sender_email.lower(),
        "reply_to_email": (reply_to_email or "").lower() or None,
        "is_active": True,
        "is_default_for_tenant": is_default_for_tenant,
        "is_default_for_client": is_default_for_client,
        "daily_send_limit": daily_send_limit,
        "monthly_send_count": 0,
        "workflow_types": workflow_types or ["generic"],
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }
    if api_key:
        doc["api_key_ref"] = encrypt(api_key)
        doc["api_key_last4"] = api_key[-4:]
    else:
        doc["api_key_ref"] = None
        doc["api_key_last4"] = ""
    return doc


def make_routing_doc(*, tenant_id: str, mailbox_id: str, workflow_type: str,
                     client_id: Optional[str] = None,
                     motivo_id: Optional[str] = None,
                     priority: int = 100,
                     description: Optional[str] = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": new_id(),
        "tenant_id": tenant_id,
        "mailbox_id": mailbox_id,
        "workflow_type": workflow_type,
        "client_id": client_id,
        "motivo_id": motivo_id,
        "priority": priority,
        "active": True,
        "description": description or "",
        "created_at": now,
        "updated_at": now,
    }


def make_send_log_doc(*, tenant_id: str, mailbox_id: Optional[str],
                      workflow_type: str, to_address: str, subject: str,
                      status: str, client_id: Optional[str] = None,
                      entity_type: Optional[str] = None,
                      entity_id: Optional[str] = None,
                      provider_message_id: Optional[str] = None,
                      error_code: Optional[str] = None,
                      error_message: Optional[str] = None) -> dict:
    import hashlib
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": new_id(),
        "tenant_id": tenant_id,
        "mailbox_id": mailbox_id,
        "client_id": client_id,
        "workflow_type": workflow_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        # Enmascarar: solo guardamos hash del subject (PII)
        "subject_hash": hashlib.sha256(subject.encode()).hexdigest(),
        # Enmascarar parcialmente el destinatario en log
        "to_masked": _mask_email(to_address),
        "provider_message_id": provider_message_id,
        "status": status,
        "error_code": error_code,
        "error_message": error_message,
        "sent_at": now,
        "delivered_at": None,
    }


def _mask_email(em: str) -> str:
    if "@" not in em:
        return em
    local, dom = em.split("@", 1)
    visible = local[:2] if len(local) > 3 else local[:1]
    return f"{visible}***@{dom}"
