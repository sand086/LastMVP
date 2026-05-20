"""OutboundWebhookDispatcher (R48) — único punto de salida de eventos.

Flujo:
  dispatch(event_type, source_id, data, tenant_id, client_id) →
    1. (R46) Idempotencia: ¿hay envío en flight (event_type, source_id) <60s?
       Si sí → reusar event_id; NO encolar de nuevo.
    2. Buscar suscripciones activas del cliente para event_type.
    3. Construir payload siguiendo schema del catálogo.
    4. Aplicar PII masking si la suscripción no tiene include_pii=true (R49).
    5. Encolar 1 job en webhook_pending_queue por suscripción + emisión.

worker_tick() (invocado por APScheduler cada 30s):
    1. Reclama hasta N jobs vencidos.
    2. Por cada job:
       - resolve_runtime(url) → IP (R45 — anti DNS rebinding)
       - sign(body, secret_v1) + opcional sign(body, secret_v2)
       - POST con timeout 30s
       - 2xx → log delivered + delete del queue
       - 4xx (no 429) → log failed_permanent + delete del queue
       - 5xx/429/timeout → reschedule con backoff o → DLQ tras 7 intentos
    3. Append SIEMPRE al webhook_delivery_log (R47).
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from core.db import get_db
from core.logger import log
from core.uuid import new_id
from repositories.webhooks import (
    WebhookDeadLetterQueueRepository,
    WebhookDeliveryLogRepository,
    WebhookPendingQueueRepository,
    WebhookSubscriptionRepository,
    WebhookEventCatalogRepository,
)
from services.ai.pii_masker import mask_dict
from services.webhooks.security import (
    decrypt_secret, sign_body,
)
from services.webhooks.url_validator import (
    SsrfBlocked, resolve_runtime,
)


# Backoff (P0.6): minutos a esperar tras intento N (N=1 inmediato)
BACKOFF_MINUTES: dict[int, int] = {
    2: 1, 3: 5, 4: 30, 5: 120, 6: 720, 7: 1440,
}
MAX_ATTEMPTS = 7
WORKER_TIMEOUT_S = float(os.environ.get("MYE_WEBHOOK_WORKER_TIMEOUT_S", "30"))
USER_AGENT = "MyExcellence-Webhook/1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


# ────────────────────────── R46 idempotencia ─────────────────────────────
async def _existing_in_flight(
    *, tenant_id: str, event_type: str, source_id: str,
) -> Optional[str]:
    """Busca un event_id de los últimos 60s para (event_type, source_id)."""
    q_repo = WebhookPendingQueueRepository(tenant_id=tenant_id)
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    doc = await q_repo.col.find_one({
        "tenant_id": tenant_id,
        "event_type": event_type,
        "source_id": source_id,
        "enqueued_at": {"$gte": cutoff},
    }, {"_id": 0, "event_id": 1}, sort=[("enqueued_at", -1)])
    return doc.get("event_id") if doc else None


# ─────────────────── PII masking selectivo (R49) ─────────────────────────
def _apply_pii_masking(payload: dict) -> dict:
    """Enmascara campos PII conocidos. Llamado cuando suscripción no tiene
    include_pii=true. Reusa el masker del AIGateway (V2)."""
    masked, _tokens = mask_dict(payload)
    return masked


# ──────────────────────────── DISPATCH (público) ─────────────────────────
async def dispatch(
    *, tenant_id: str, client_id: str,
    event_type: str, source_id: str, data: dict,
) -> dict:
    """Punto único de emisión. Idempotente por (event_type, source_id) <60s.

    Devuelve `{event_id, queued_count, reused_in_flight: bool}`.
    """
    # 1. Validar evento contra catálogo
    cat = await WebhookEventCatalogRepository(tenant_id=tenant_id).by_code(event_type)
    if not cat:
        log.warning("webhook_event_unknown", extra={"context": {
            "event_type": event_type, "source_id": source_id,
        }})
        return {"event_id": None, "queued_count": 0, "reused_in_flight": False,
                "error": "EVENT_NOT_IN_CATALOG"}

    # 2. R46 — idempotencia: reusar event_id si existe in-flight
    existing = await _existing_in_flight(
        tenant_id=tenant_id, event_type=event_type, source_id=source_id,
    )
    if existing:
        return {"event_id": existing, "queued_count": 0, "reused_in_flight": True}

    # 3. Buscar suscripciones que escuchan este evento
    sub_repo = WebhookSubscriptionRepository(tenant_id=tenant_id)
    subs = await sub_repo.find_subscribers_for_event(
        client_id=client_id, event_code=event_type,
    )
    if not subs:
        return {"event_id": None, "queued_count": 0, "reused_in_flight": False}

    event_id = new_id()
    occurred_at = _now_iso()
    queue = WebhookPendingQueueRepository(tenant_id=tenant_id)

    queued = 0
    for sub in subs:
        # Filtros JSONPath (P2) — soporta dict simple legacy + expresiones $....
        from services.webhooks.filter import evaluate_filter
        full_payload_for_filter = {
            "event_type": event_type, "data": data,
        }
        if not evaluate_filter(
            filter_spec=sub.get("filter_jsonpath"),
            payload=full_payload_for_filter,
        ):
            continue

        # PII masking según R49
        applied_data = data
        pii_masked = False
        if cat.get("contains_pii") and not sub.get("include_pii"):
            applied_data = _apply_pii_masking(data)
            pii_masked = True

        payload = {
            "event_id": event_id,
            "event_type": event_type,
            "schema_version": cat["schema_version"],
            "occurred_at": occurred_at,
            "tenant_id": tenant_id,
            "data": applied_data,
        }
        await queue.enqueue({
            "subscription_id": sub["id"],
            "client_id": client_id,
            "event_id": event_id,
            "event_type": event_type,
            "source_id": source_id,
            "payload": payload,
            "pii_masked": pii_masked,
        })
        queued += 1
    log.info("webhook_dispatched", extra={"context": {
        "event_type": event_type, "source_id": source_id,
        "event_id": event_id, "queued": queued,
    }})
    return {"event_id": event_id, "queued_count": queued,
            "reused_in_flight": False}


# ──────────────────────────── WORKER ─────────────────────────────────────
async def _send_one(*, sub: dict, payload: dict) -> tuple[str, int | None,
                                                          int | None, str | None,
                                                          str | None, str | None]:
    """Devuelve (status, http_status_code, latency_ms, response_preview,
    error_message, resolved_ip).

    `status` ∈ delivered/failed_temporary/failed_permanent/timeout/blocked_ssrf
    """
    url = sub["endpoint_url"]
    # R45 — anti DNS rebinding: revalidar DNS por request
    try:
        ip = resolve_runtime(url)
    except SsrfBlocked as e:
        return ("blocked_ssrf", None, None, None, e.message, None)

    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "X-MyE-Event": payload["event_type"],
        "X-MyE-Event-Id": payload["event_id"],
        "X-MyE-Schema-Version": payload["schema_version"],
        "X-MyE-Timestamp": str(int(datetime.now(timezone.utc).timestamp())),
        "X-MyE-Subscription-Id": sub["id"],
    }
    # Firma con secreto v1
    secret_v1 = decrypt_secret(sub["hmac_secret_encrypted"])
    headers["X-MyE-Signature"] = sign_body(secret=secret_v1, body=body)
    # Firma adicional v2 si está activa (P1.3 rotación con grace)
    if sub.get("hmac_secret_v2_encrypted") and sub.get("hmac_v2_until"):
        if sub["hmac_v2_until"] > _now_iso():
            secret_v2 = decrypt_secret(sub["hmac_secret_v2_encrypted"])
            headers["X-MyE-Signature-V2"] = sign_body(secret=secret_v2, body=body)

    started = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=WORKER_TIMEOUT_S, follow_redirects=False) as c:
            r = await c.post(url, content=body, headers=headers)
        latency_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        preview = (r.text or "")[:1024]
        if 200 <= r.status_code < 300:
            return ("delivered", r.status_code, latency_ms, preview, None, ip)
        if r.status_code in (429,) or 500 <= r.status_code < 600:
            return ("failed_temporary", r.status_code, latency_ms, preview,
                    f"http_{r.status_code}", ip)
        return ("failed_permanent", r.status_code, latency_ms, preview,
                f"http_{r.status_code}", ip)
    except httpx.TimeoutException as e:
        latency_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        return ("timeout", None, latency_ms, None, str(e)[:200], ip)
    except Exception as e:  # noqa: BLE001
        latency_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        return ("failed_temporary", None, latency_ms, None,
                type(e).__name__ + ": " + str(e)[:200], ip)


async def _process_job(job: dict) -> None:
    tenant_id = job["tenant_id"]
    sub_repo = WebhookSubscriptionRepository(tenant_id=tenant_id)
    queue = WebhookPendingQueueRepository(tenant_id=tenant_id)
    log_repo = WebhookDeliveryLogRepository(tenant_id=tenant_id)
    dlq_repo = WebhookDeadLetterQueueRepository(tenant_id=tenant_id)

    sub = await sub_repo.get_decrypted(job["subscription_id"])
    if not sub or not sub.get("is_active"):
        # Suscripción borrada/desactivada → log y eliminar
        await log_repo.append({
            "subscription_id": job["subscription_id"],
            "event_id": job["event_id"],
            "event_code": job["event_type"],
            "source_id": job.get("source_id"),
            "schema_version": job["payload"].get("schema_version", "v1"),
            "attempt_number": job.get("attempt_number", 0) + 1,
            "payload_hash": hashlib.sha256(
                json.dumps(job["payload"], separators=(",", ":")).encode()
            ).hexdigest(),
            "payload_size_bytes": 0,
            "pii_masked": job.get("pii_masked", False),
            "endpoint_url_hash": "",
            "status": "failed_permanent",
            "error_message": "subscription_inactive_or_deleted",
        })
        await queue.delete(job["id"])
        return

    # P2 — Burst mode: si is_paused=true, conservar el evento en queue y
    # reagendar sin contar el intento. Permite al admin "pausar" sin perder
    # eventos (distinto a is_active=false que sí descarta).
    if sub.get("is_paused"):
        await log_repo.append({
            "subscription_id": sub["id"],
            "event_id": job["event_id"],
            "event_code": job["event_type"],
            "source_id": job.get("source_id"),
            "schema_version": job["payload"].get("schema_version", "v1"),
            "attempt_number": job.get("attempt_number", 0) + 1,
            "payload_hash": "",
            "payload_size_bytes": 0,
            "pii_masked": job.get("pii_masked", False),
            "endpoint_url_hash": _hash_url(sub["endpoint_url"]),
            "status": "paused",
            "error_message": "subscription_paused_by_admin",
        })
        next_run = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        await queue.reschedule(
            job["id"], next_run_at=next_run,
            attempt_number=job.get("attempt_number", 0),
        )
        return

    # P1.1 circuit breaker — si circuito abierto, log y reschedule
    if sub.get("is_circuit_open") and sub.get("circuit_open_until", "") > _now_iso():
        await log_repo.append({
            "subscription_id": sub["id"],
            "event_id": job["event_id"],
            "event_code": job["event_type"],
            "source_id": job.get("source_id"),
            "schema_version": job["payload"].get("schema_version", "v1"),
            "attempt_number": job.get("attempt_number", 0) + 1,
            "payload_hash": "",
            "payload_size_bytes": 0,
            "pii_masked": job.get("pii_masked", False),
            "endpoint_url_hash": _hash_url(sub["endpoint_url"]),
            "status": "circuit_open",
            "error_message": "circuit_open_until=" + str(sub.get("circuit_open_until")),
        })
        next_run = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        await queue.reschedule(
            job["id"], next_run_at=next_run,
            attempt_number=job.get("attempt_number", 0),
        )
        return

    payload = job["payload"]
    body_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_hash = hashlib.sha256(body_bytes).hexdigest()
    attempt_number = job.get("attempt_number", 0) + 1

    status, http_code, latency_ms, preview, err, ip = await _send_one(
        sub=sub, payload=payload,
    )

    await log_repo.append({
        "subscription_id": sub["id"],
        "event_id": job["event_id"],
        "event_code": job["event_type"],
        "source_id": job.get("source_id"),
        "schema_version": payload.get("schema_version", "v1"),
        "attempt_number": attempt_number,
        "payload_hash": payload_hash,
        "payload_size_bytes": len(body_bytes),
        "pii_masked": job.get("pii_masked", False),
        "endpoint_url_hash": _hash_url(sub["endpoint_url"]),
        "resolved_ip": ip,
        "status": status,
        "http_status_code": http_code,
        "response_body_preview": preview,
        "latency_ms": latency_ms,
        "error_message": err,
    })

    # P1.1 — Circuit breaker: evaluar tras cada intento
    from services.webhooks.circuit_breaker import (
        evaluate_and_trip, reset_after_success,
    )
    try:
        if status == "delivered":
            await reset_after_success(
                tenant_id=tenant_id, subscription_id=sub["id"],
            )
        else:
            await evaluate_and_trip(
                tenant_id=tenant_id, subscription_id=sub["id"],
            )
    except Exception:  # noqa: BLE001
        log.exception("webhook_cb_eval_failed", extra={"context": {
            "subscription_id": sub["id"], "status": status,
        }})

    if status in ("delivered", "failed_permanent", "blocked_ssrf"):
        await queue.delete(job["id"])
        return

    # status ∈ {failed_temporary, timeout}
    if attempt_number >= MAX_ATTEMPTS:
        await dlq_repo.enqueue({
            "subscription_id": sub["id"],
            "event_id": job["event_id"],
            "event_code": job["event_type"],
            "payload": payload,
            "attempts_made": attempt_number,
            "last_status": status,
            "last_error": err,
            "first_failed_at": job.get("enqueued_at", _now_iso()),
        })
        await queue.delete(job["id"])
        log.warning("webhook_to_dlq", extra={"context": {
            "event_id": job["event_id"], "subscription_id": sub["id"],
            "attempts": attempt_number,
        }})
        return

    # Reagendar con backoff
    backoff = BACKOFF_MINUTES.get(attempt_number + 1, 60)
    next_run = (datetime.now(timezone.utc) + timedelta(minutes=backoff)).isoformat()
    await queue.reschedule(
        job["id"], next_run_at=next_run, attempt_number=attempt_number,
    )


async def worker_tick(*, batch: int = 25) -> dict:
    """Una pasada del worker. Procesa todos los jobs vencidos en todos los
    tenants. Retorna métricas para observabilidad."""
    db = get_db()
    # Reclamar jobs vencidos en cualquier tenant. Construimos la query manual
    # porque WebhookPendingQueueRepository requiere tenant_id.
    now = _now_iso()
    coll = db["webhook_pending_queue"]
    processed = 0
    for _ in range(batch):
        doc = await coll.find_one_and_update(
            {"$and": [
                {"next_run_at": {"$lte": now}},
                {"$or": [{"claimed_at": None}, {"claimed_at": {"$exists": False}}]},
            ]},
            {"$set": {"claimed_at": now}},
            projection={"_id": 0},
            return_document=True,
        )
        if doc is None:
            break
        try:
            await _process_job(doc)
            processed += 1
        except Exception:  # noqa: BLE001
            log.exception("webhook_worker_job_failed", extra={"context": {
                "job_id": doc.get("id"),
            }})
    return {"processed": processed, "ts": now}


# Helper sincrónico para tests
def fire_and_forget(coro) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        pass


# Export pública del dispatcher (R48 — único punto)
class OutboundWebhookDispatcher:
    """Wrapper sin estado para que las features llamen
    `OutboundWebhookDispatcher.dispatch(...)`. Ver R48."""
    @staticmethod
    async def dispatch(*, tenant_id: str, client_id: str,
                        event_type: str, source_id: str, data: dict) -> dict:
        return await dispatch(
            tenant_id=tenant_id, client_id=client_id,
            event_type=event_type, source_id=source_id, data=data,
        )

    @staticmethod
    async def worker_tick(*, batch: int = 25) -> dict:
        return await worker_tick(batch=batch)


__all__ = ["OutboundWebhookDispatcher", "dispatch", "worker_tick",
           "BACKOFF_MINUTES", "MAX_ATTEMPTS"]
