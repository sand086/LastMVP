"""TenantEmailSettings — per-tenant Resend credentials & sender identity.

Cada tenant puede configurar:
  * Su propia API key de Resend (encriptada con Fernet).
  * Su propia identidad de remitente (`sender_email`, `sender_name`).
  * `reply_to_default` opcional.

Si un tenant no tiene config (o está disabled), el servicio cae a las variables
de entorno globales (`RESEND_API_KEY`, `SENDER_EMAIL`, `SENDER_NAME`) — esto
mantiene backwards-compat con tenants que aún no han migrado.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from core.crypto import encrypt, decrypt
from core.db import get_db
from core.logger import log


COLLECTION = "tenant_email_settings"


async def get_settings(tenant_id: str) -> Optional[dict]:
    """Read-only fetch; api_key NUNCA se devuelve descifrada."""
    db = get_db()
    doc = await db[COLLECTION].find_one(
        {"tenant_id": tenant_id}, {"_id": 0},
    )
    return doc


async def get_public_view(tenant_id: str) -> dict:
    """Vista pública para la UI: oculta la API key, devuelve indicadores."""
    doc = await get_settings(tenant_id) or {}
    has_key = bool(doc.get("api_key_ref"))
    return {
        "configured": has_key,
        "status": doc.get("status", "disabled"),
        "sender_email": doc.get("sender_email", ""),
        "sender_name": doc.get("sender_name", ""),
        "reply_to_default": doc.get("reply_to_default", ""),
        "domain_verified": doc.get("domain_verified", False),
        # Solo mostramos los últimos 4 chars de la API key para confirmación visual
        "api_key_hint": ("****" + doc["api_key_last4"]) if doc.get("api_key_last4") else "",
        "updated_at": doc.get("updated_at"),
        "last_test_at": doc.get("last_test_at"),
        "last_test_ok": doc.get("last_test_ok"),
        "last_test_error": doc.get("last_test_error"),
    }


async def upsert(
    *, tenant_id: str, actor_id: str,
    sender_email: str, sender_name: str,
    api_key: Optional[str] = None,
    reply_to_default: Optional[str] = None,
    status: str = "active",
) -> dict:
    """Crea o actualiza la config. ``api_key`` solo se actualiza si viene
    no-nula (None = preservar la existente).
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    update: dict = {
        "tenant_id": tenant_id,
        "sender_email": sender_email,
        "sender_name": sender_name,
        "reply_to_default": reply_to_default or "",
        "status": status,
        "updated_at": now,
        "updated_by": actor_id,
    }
    if api_key:
        update["api_key_ref"] = encrypt(api_key)
        update["api_key_last4"] = api_key[-4:]
    await db[COLLECTION].update_one(
        {"tenant_id": tenant_id},
        {"$set": update, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    log.info("tenant_email_settings_upsert", extra={"context": {
        "tenant_id": tenant_id, "actor_id": actor_id,
        "api_key_changed": bool(api_key),
    }})
    return await get_public_view(tenant_id)


async def resolve_credentials(tenant_id: str) -> dict:
    """Devuelve `{api_key, sender_email, sender_name, reply_to_default, source}`
    listo para usar por NotificationService.

    Si el tenant tiene config activa, usa esa. Caso contrario, fallback a env
    globales (mantiene backwards-compat).
    """
    from core.config import RESEND_API_KEY, SENDER_EMAIL, SENDER_NAME

    doc = await get_settings(tenant_id) or {}
    if doc.get("status") == "active" and doc.get("api_key_ref"):
        try:
            return {
                "api_key": decrypt(doc["api_key_ref"]),
                "sender_email": doc.get("sender_email") or SENDER_EMAIL,
                "sender_name": doc.get("sender_name") or SENDER_NAME,
                "reply_to_default": doc.get("reply_to_default") or "",
                "source": "tenant",
            }
        except ValueError:
            log.error("tenant_email_settings_decrypt_failed",
                      extra={"context": {"tenant_id": tenant_id}})
    return {
        "api_key": RESEND_API_KEY or "",
        "sender_email": SENDER_EMAIL or "",
        "sender_name": SENDER_NAME or "",
        "reply_to_default": "",
        "source": "env",
    }


async def record_test_result(*, tenant_id: str, ok: bool,
                              error: Optional[str] = None) -> None:
    db = get_db()
    await db[COLLECTION].update_one(
        {"tenant_id": tenant_id},
        {"$set": {
            "last_test_at": datetime.now(timezone.utc).isoformat(),
            "last_test_ok": ok,
            "last_test_error": error or "",
        }},
    )
