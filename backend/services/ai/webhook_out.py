"""Outbound webhook — envía drafts aprobados al endpoint del cliente (P1 · PROMPT 26).

Cuando un agente APRUEBA un draft (`/api/ai/invocations/{id}/approve`), si el
cliente tiene `webhook_outbound_url` configurado, se firma el payload con
HMAC SHA-256 (header `X-MyE-Signature: sha256=<hex>`) y se entrega.

Reintentos: 3 con backoff exponencial (0.5s · 1.5s · 4.5s). Si tras 3 reintentos
falla, se persiste `webhook_delivered: false` en el log de invocación. La
operación NO bloquea la respuesta al agente — corre como tarea asíncrona.
"""
from __future__ import annotations
import asyncio
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone

import httpx

from core.logger import log
from core.db import get_db

_WEBHOOK_TIMEOUT_S = float(os.environ["AI_WEBHOOK_TIMEOUT_S"])
_WEBHOOK_RETRIES = int(os.environ["AI_WEBHOOK_RETRIES"])


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()


async def deliver(*, tenant_id: str, invocation_id: str, payload: dict,
                  url: str, secret: str | None) -> dict:
    """Best-effort delivery con reintentos. Devuelve el último estado."""
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "MyExcellence/AI-1.0"}
    if secret:
        headers["X-MyE-Signature"] = _sign(secret, body)
    last_err = None
    for attempt in range(1, _WEBHOOK_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=_WEBHOOK_TIMEOUT_S) as client:
                r = await client.post(url, content=body, headers=headers)
                if 200 <= r.status_code < 300:
                    log.info("ai_webhook_delivered", extra={"context": {
                        "invocation_id": invocation_id, "status": r.status_code,
                        "attempt": attempt,
                    }})
                    await _mark_delivered(tenant_id, invocation_id, True,
                                          status_code=r.status_code, attempt=attempt)
                    return {"ok": True, "status_code": r.status_code, "attempt": attempt}
                last_err = f"http_{r.status_code}"
        except Exception as e:  # noqa: BLE001
            last_err = type(e).__name__ + ": " + str(e)[:120]
        # backoff: 0.5 · 1.5 · 4.5
        await asyncio.sleep(0.5 * (3 ** (attempt - 1)))
    log.warning("ai_webhook_failed", extra={"context": {
        "invocation_id": invocation_id, "url": url[:80], "last_err": last_err,
    }})
    await _mark_delivered(tenant_id, invocation_id, False, status_code=None,
                          attempt=_WEBHOOK_RETRIES, error=last_err)
    return {"ok": False, "error": last_err, "attempt": _WEBHOOK_RETRIES}


async def _mark_delivered(tenant_id: str, invocation_id: str, ok: bool,
                          *, status_code: int | None, attempt: int,
                          error: str | None = None) -> None:
    db = get_db()
    await db.ai_invocation_log.update_one(
        {"id": invocation_id, "tenant_id": tenant_id},
        {"$set": {
            "webhook_delivered": ok,
            "webhook_status_code": status_code,
            "webhook_attempt": attempt,
            "webhook_error": error,
            "webhook_delivered_at": datetime.now(timezone.utc).isoformat(),
        }},
    )


def fire_and_forget(*, tenant_id: str, invocation_id: str, payload: dict,
                    url: str, secret: str | None) -> None:
    """Lanza el delivery en background sin bloquear el caller."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(deliver(
            tenant_id=tenant_id, invocation_id=invocation_id, payload=payload,
            url=url, secret=secret,
        ))
    except RuntimeError:
        # No event loop — skip
        pass
