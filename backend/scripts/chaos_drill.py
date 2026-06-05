#!/usr/bin/env python3
"""Chaos drill — PROMPT 39 V3 P2.

Genera N eventos via OutboundWebhookDispatcher contra una suscripción real
apuntando al endpoint público /api/webhook-test/echo, con failure modes
controlados (fail_rate, slow_ms, status). Mide:

  - Eventos enviados
  - Recibidos en el receptor (signature_valid count)
  - Failed → DLQ
  - Reintentos por evento
  - Latencia p50/p95/p99
  - Circuit breaker activations

Uso (como script):
  python -m scripts.chaos_drill --tenant TENANT_ID --client CLIENT_ID \
                                 --total 1000 --fail-rate 30

Como módulo:
  from scripts.chaos_drill import run_drill
  await run_drill(tenant_id=..., client_id=..., total=1000, fail_rate=30)
"""
from __future__ import annotations
import argparse
import asyncio
import os
import statistics
import sys
import time
from datetime import datetime, timezone

# Path setup
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from core.db import get_db  # noqa: E402


async def _ensure_subscription(*, tenant_id: str, client_id: str,
                                target_url: str, fail_rate: int = 0,
                                slow_ms: int = 0) -> str:
    """Crea (o reusa) una suscripción para el drill apuntando al echo público."""
    from repositories.webhooks import (
        WebhookSubscriptionRepository, ensure_webhook_indexes,
    )
    from services.webhooks.security import encrypt_secret
    from seeds.webhook_catalog import run as seed
    await seed()
    await ensure_webhook_indexes()

    repo = WebhookSubscriptionRepository(tenant_id=tenant_id)
    qs = []
    if fail_rate:
        qs.append(f"fail_rate={fail_rate}")
    if slow_ms:
        qs.append(f"slow_ms={slow_ms}")
    full_url = target_url + ("?" + "&".join(qs) if qs else "")
    # Buscar existente (mismo URL exacto)
    existing = await repo.col.find_one({
        "tenant_id": tenant_id, "client_id": client_id,
        "endpoint_url": full_url,
    }, {"_id": 0, "id": 1})
    if existing:
        return existing["id"]
    secret = os.environ["MYE_WEBHOOK_TEST_SECRET"]
    sub = await repo.create({
        "client_id": client_id,
        "endpoint_url": full_url,
        "endpoint_url_hash": "",
        "hmac_secret_encrypted": encrypt_secret(secret),
        "event_codes": ["ticket.created"],
        "include_pii": False, "is_active": True,
    })
    return sub["id"]


async def run_drill(*, tenant_id: str, client_id: str, total: int = 1000,
                     fail_rate: int = 0, slow_ms: int = 0,
                     target_url: str | None = None) -> dict:
    """Ejecuta el drill. Devuelve un dict con métricas."""
    from services.webhooks.dispatcher import dispatch, worker_tick

    base = os.environ["MYE_BASE_URL"]
    target = target_url or f"{base}/api/webhook-test/echo"
    sub_id = await _ensure_subscription(
        tenant_id=tenant_id, client_id=client_id, target_url=target,
        fail_rate=fail_rate, slow_ms=slow_ms,
    )

    # Limpiar receptor
    db = get_db()
    await db.webhook_test_received.delete_many({})

    print(f"🎯 Drill: {total} eventos · fail_rate={fail_rate}% · slow={slow_ms}ms")
    print(f"   Subscription: {sub_id} → {target}")

    started = time.perf_counter()
    dispatched_count = 0
    for i in range(total):
        res = await dispatch(
            tenant_id=tenant_id, client_id=client_id,
            event_type="ticket.created",
            source_id=f"chaos-{int(time.time())}-{i}",
            data={"ticket": {"id": f"INC-{i}", "status": "pending"}},
        )
        if res.get("queued_count"):
            dispatched_count += 1
    elapsed_dispatch = time.perf_counter() - started
    print(f"📤 Dispatched {dispatched_count} eventos en {elapsed_dispatch:.2f}s "
          f"({dispatched_count/elapsed_dispatch:.0f} ev/s)")

    # Pump worker hasta vaciar la queue (max 30 ticks)
    print("⚡ Procesando worker…")
    started_worker = time.perf_counter()
    for tick in range(60):
        await worker_tick(batch=200)
        pending = await db.webhook_pending_queue.count_documents({})
        # Reset next_run_at de los que están reagendados al futuro para acelerar
        await db.webhook_pending_queue.update_many(
            {}, {"$set": {"next_run_at": datetime.now(timezone.utc).isoformat(),
                          "claimed_at": None}},
        )
        if pending == 0:
            break
    elapsed_worker = time.perf_counter() - started_worker
    print(f"⚡ Worker drenó queue en {elapsed_worker:.2f}s")

    # Métricas finales
    received = await db.webhook_test_received.count_documents({})
    sig_ok = await db.webhook_test_received.count_documents({"signature_valid": True})
    delivered = await db.webhook_delivery_log.count_documents(
        {"tenant_id": tenant_id, "subscription_id": sub_id, "status": "delivered"},
    )
    failures = await db.webhook_delivery_log.count_documents(
        {"tenant_id": tenant_id, "subscription_id": sub_id,
         "status": {"$in": ["failed_temporary", "failed_permanent",
                            "timeout", "circuit_open"]}},
    )
    dlq = await db.webhook_dead_letter_queue.count_documents(
        {"tenant_id": tenant_id, "subscription_id": sub_id, "resolved": False},
    )
    cb_open = await db.webhook_subscriptions.find_one(
        {"id": sub_id, "tenant_id": tenant_id}, {"_id": 0, "is_circuit_open": 1},
    )

    # Latencias
    cursor = db.webhook_delivery_log.find(
        {"tenant_id": tenant_id, "subscription_id": sub_id, "latency_ms": {"$ne": None}},
        {"_id": 0, "latency_ms": 1},
    )
    lats = [d["latency_ms"] async for d in cursor if d.get("latency_ms")]
    p50 = statistics.median(lats) if lats else 0
    p95 = statistics.quantiles(lats, n=20)[18] if len(lats) >= 20 else 0
    p99 = statistics.quantiles(lats, n=100)[98] if len(lats) >= 100 else 0

    metrics = {
        "total_dispatched": dispatched_count,
        "total_received_by_echo": received,
        "signature_valid_received": sig_ok,
        "delivered": delivered,
        "failures": failures,
        "dlq": dlq,
        "circuit_open": bool(cb_open and cb_open.get("is_circuit_open")),
        "latency_p50_ms": round(p50, 1),
        "latency_p95_ms": round(p95, 1),
        "latency_p99_ms": round(p99, 1),
        "dispatch_throughput_ev_s": round(dispatched_count / elapsed_dispatch, 1),
        "worker_drain_s": round(elapsed_worker, 2),
    }
    print()
    print("📊 Resultados:")
    for k, v in metrics.items():
        print(f"   {k:32s} {v}")
    return metrics


async def main():
    parser = argparse.ArgumentParser(description="Webhooks chaos drill")
    parser.add_argument("--tenant", required=True, help="Tenant ID")
    parser.add_argument("--client", required=True, help="Client ID")
    parser.add_argument("--total", type=int, default=100, help="Eventos a generar")
    parser.add_argument("--fail-rate", type=int, default=0, help="% chaos failures")
    parser.add_argument("--slow-ms", type=int, default=0, help="Latencia echo")
    parser.add_argument("--target", default=None, help="URL del echo (override)")
    args = parser.parse_args()
    await run_drill(
        tenant_id=args.tenant, client_id=args.client, total=args.total,
        fail_rate=args.fail_rate, slow_ms=args.slow_ms, target_url=args.target,
    )


if __name__ == "__main__":
    asyncio.run(main())
