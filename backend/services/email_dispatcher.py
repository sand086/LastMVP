"""Bundle G · EmailDispatcher — único punto de salida de correos (BP-06).

Implementa:
  * resolve_mailbox(context)  — algoritmo de especificidad (E2.2).
  * send(context, payload)    — emite vía Resend, registra en email_send_log.

R53: si la resolución no encuentra buzón aplicable, fallar VISIBLE con
``error_code='NO_MAILBOX_RESOLVED'``. NUNCA inventar default arbitrario.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from core.crypto import decrypt
from core.logger import log
from core.uuid import new_id
from models.email_multibuzon import EmailContext, EmailPayload, SendResult
from repositories.email_multibuzon import (
    EmailDomainRepository, EmailMailboxRepository,
    EmailRoutingRepository, EmailSendLogRepository,
    make_send_log_doc,
)


class EmailDispatcher:
    """Stateless dispatcher — los repos llevan el scope por tenant."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.domains = EmailDomainRepository(tenant_id=tenant_id)
        self.mailboxes = EmailMailboxRepository(tenant_id=tenant_id)
        self.routing = EmailRoutingRepository(tenant_id=tenant_id)
        self.send_log = EmailSendLogRepository(tenant_id=tenant_id)

    # ─────────────────────────────────────────────────────────
    async def resolve_mailbox(self, context: EmailContext) -> Optional[dict]:
        """Devuelve el documento de mailbox que aplica al contexto, o None.

        Orden (E2.2):
          1. explicit_mailbox_id override.
          2. Reglas en email_routing por especificidad descendente:
             (tenant + client + motivo + workflow) > (tenant + client + workflow)
             > (tenant + motivo + workflow) > (tenant + workflow).
          3. Default del cliente (is_default_for_client=true).
          4. Default del tenant (is_default_for_tenant=true).
          5. None.
        """
        # 1) Explicit override
        if context.explicit_mailbox_id:
            mb = await self.mailboxes.find_one(
                {"id": context.explicit_mailbox_id})
            if mb and mb.get("is_active"):
                return mb
            return None

        # 2) Reglas de routing ordenadas por especificidad
        rules = await self.routing.find_matching(
            workflow_type=context.workflow_type,
            client_id=context.client_id,
            motivo_id=context.motivo_id,
        )
        for rule in rules:
            mb = await self.mailboxes.find_one({"id": rule["mailbox_id"]})
            if mb and mb.get("is_active"):
                return mb
            # Si el mailbox de la regla está inactivo, ignorar regla y seguir.

        # 3) Default del cliente
        if context.client_id:
            mb = await self.mailboxes.find_default_for_client(context.client_id)
            if mb:
                return mb

        # 4) Default del tenant
        mb = await self.mailboxes.find_default_for_tenant()
        if mb:
            return mb

        # 5) Sin match
        return None

    # ─────────────────────────────────────────────────────────
    async def send(self, context: EmailContext, payload: EmailPayload) -> SendResult:
        """Envía el correo usando el mailbox resuelto. Append-only log."""
        # 1) Resolver
        mb = await self.resolve_mailbox(context)
        if not mb:
            return await self._record_failure(
                context, payload,
                mailbox_id=None,
                error_code="NO_MAILBOX_RESOLVED",
                error_message=(
                    "No hay buzón configurado para este contexto. "
                    "Configurá la matriz de ruteo o un buzón default."),
            )

        # 2) Verificar dominio
        domain = await self.domains.find_one({"id": mb["domain_id"]})
        if not domain:
            return await self._record_failure(
                context, payload, mailbox_id=mb["id"],
                error_code="DOMAIN_NOT_FOUND",
                error_message="El dominio del buzón no existe.",
            )
        if domain.get("verification_status") != "verified" or domain.get("degraded"):
            return await self._record_failure(
                context, payload, mailbox_id=mb["id"],
                error_code="DOMAIN_NOT_VERIFIED",
                error_message=(
                    f"El dominio {domain['domain']} no está verificado o está "
                    "degradado. Verificalo en /admin/email-settings."),
            )

        # 3) Verificar quota diaria
        if mb.get("daily_send_limit"):
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0).isoformat()
            sent_today = await self.send_log.col.count_documents({
                "tenant_id": self.tenant_id,
                "mailbox_id": mb["id"],
                "sent_at": {"$gte": today_start},
                "status": {"$in": ["sent", "queued"]},
            })
            if sent_today >= mb["daily_send_limit"]:
                return await self._record_failure(
                    context, payload, mailbox_id=mb["id"],
                    error_code="QUOTA_EXCEEDED",
                    error_message=(
                        f"Buzón alcanzó el límite diario "
                        f"({mb['daily_send_limit']} envíos)."),
                )

        # 4) Construir y enviar vía Resend
        api_key = self._decrypt_api_key(mb)
        if not api_key:
            # Mock send (CI / dev) — registramos como queued para trazabilidad
            doc = make_send_log_doc(
                tenant_id=self.tenant_id, mailbox_id=mb["id"],
                client_id=context.client_id,
                workflow_type=context.workflow_type,
                entity_type=context.entity_type, entity_id=context.entity_id,
                to_address=payload.to[0], subject=payload.subject,
                status="sent",
                provider_message_id=f"mock_{new_id()}",
            )
            await self.send_log.insert(doc)
            return SendResult(
                success=True, status="sent",
                provider_message_id=doc["provider_message_id"],
                log_id=doc["id"], mailbox_id=mb["id"], mock=True,
            )

        # 5) Envío real vía Resend
        result = await self._send_via_resend(
            api_key=api_key,
            from_header=f"{mb['sender_name']} <{mb['sender_email']}>",
            reply_to=mb.get("reply_to_email"),
            payload=payload,
            tags={
                "tenant_id": self.tenant_id[:8],
                "workflow": context.workflow_type,
                **(payload.tags or {}),
            },
        )
        doc = make_send_log_doc(
            tenant_id=self.tenant_id, mailbox_id=mb["id"],
            client_id=context.client_id,
            workflow_type=context.workflow_type,
            entity_type=context.entity_type, entity_id=context.entity_id,
            to_address=payload.to[0], subject=payload.subject,
            status="sent" if result["ok"] else "failed",
            provider_message_id=result.get("id"),
            error_code=result.get("error_code"),
            error_message=result.get("error"),
        )
        await self.send_log.insert(doc)
        if result["ok"]:
            await self.mailboxes.col.update_one(
                {"id": mb["id"]},
                {"$inc": {"monthly_send_count": 1}},
            )
        return SendResult(
            success=result["ok"],
            status="sent" if result["ok"] else "failed",
            provider_message_id=result.get("id"),
            error_code=result.get("error_code"),
            error_message=result.get("error"),
            log_id=doc["id"],
            mailbox_id=mb["id"],
        )

    # ─────────────────────────────────────────────────────────
    async def _record_failure(self, context: EmailContext, payload: EmailPayload,
                               *, mailbox_id: Optional[str],
                               error_code: str, error_message: str) -> SendResult:
        doc = make_send_log_doc(
            tenant_id=self.tenant_id, mailbox_id=mailbox_id,
            client_id=context.client_id,
            workflow_type=context.workflow_type,
            entity_type=context.entity_type, entity_id=context.entity_id,
            to_address=payload.to[0] if payload.to else "(unknown)",
            subject=payload.subject,
            status="failed",
            error_code=error_code, error_message=error_message,
        )
        await self.send_log.insert(doc)
        log.error("email_dispatcher_failed", extra={"context": {
            "tenant_id": self.tenant_id, "error_code": error_code,
            "workflow_type": context.workflow_type,
            "client_id": context.client_id,
        }})
        return SendResult(
            success=False, status="failed",
            error_code=error_code, error_message=error_message,
            log_id=doc["id"], mailbox_id=mailbox_id,
        )

    @staticmethod
    def _decrypt_api_key(mb: dict) -> Optional[str]:
        ref = mb.get("api_key_ref")
        if not ref:
            return None
        try:
            return decrypt(ref)
        except Exception:  # noqa: BLE001
            log.error("email_dispatcher_decrypt_failed",
                      extra={"context": {"mailbox_id": mb.get("id")}})
            return None

    @staticmethod
    async def _send_via_resend(*, api_key: str, from_header: str,
                                reply_to: Optional[str],
                                payload: EmailPayload, tags: dict) -> dict:
        import asyncio
        import resend
        resend.api_key = api_key
        params: dict = {
            "from": from_header,
            "to": payload.to,
            "subject": payload.subject,
            "html": payload.body_html,
        }
        if payload.cc:
            params["cc"] = payload.cc
        if payload.bcc:
            params["bcc"] = payload.bcc
        if payload.body_text:
            params["text"] = payload.body_text
        if reply_to:
            params["reply_to"] = reply_to
        if tags:
            params["tags"] = [{"name": k, "value": str(v)} for k, v in tags.items()]
        try:
            result = await asyncio.to_thread(resend.Emails.send, params)
            msg_id = result.get("id") if isinstance(result, dict) else None
            return {"ok": True, "id": msg_id}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "id": None,
                    "error": str(e), "error_code": "PROVIDER_ERROR"}
