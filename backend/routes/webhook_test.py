"""Public webhook ECHO endpoint — testing harness para PROMPT 39 V3 P2.

Endpoint: POST /api/webhook-test/echo

Acepta cualquier body JSON, valida la firma HMAC contra un secreto compartido
en `MYE_WEBHOOK_TEST_SECRET` y devuelve metadata sobre lo recibido.
Útil para que un cliente verifique end-to-end cómo se ve un evento sin
tener que montar su propio receptor.

Para chaos testing: puede simular failures vía query params:
  - ?fail_rate=30       → 30% requests devuelven 500
  - ?slow_ms=5000       → demora 5000ms antes de responder
  - ?status=429         → siempre devuelve ese status
  - ?fail_until=2027-01-01T00:00:00Z → falla hasta esa fecha

Guardamos los eventos recibidos en `webhook_test_received` (cap 1000).
"""
from __future__ import annotations
import asyncio
import hashlib
import hmac
import json
import os
import random
from datetime import datetime, timezone

from fastapi import APIRouter, Header, Query, Request

from core.db import get_db
from core.logger import log
from core.response import ok
from core.uuid import new_id


router = APIRouter(prefix="/api/webhook-test", tags=["webhook-test"])

CAP = 1000
TEST_SECRET = os.environ["MYE_WEBHOOK_TEST_SECRET"]


def _verify(body: bytes, signature: str) -> bool:
    expected = "sha256=" + hmac.new(
        TEST_SECRET.encode("utf-8"), body, hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


@router.post("/echo")
async def echo(
    request: Request,
    fail_rate: int = Query(default=0, ge=0, le=100,
                            description="% requests que devuelven 500"),
    slow_ms: int = Query(default=0, ge=0, le=60000,
                          description="Latencia artificial antes de responder"),
    status_override: int = Query(default=0, alias="status",
                                  description="Forzar HTTP status (0=normal)"),
    fail_until: str | None = Query(default=None,
                                     description="ISO8601 — hasta esa hora todo falla 503"),
    x_mye_signature: str | None = Header(default=None),
    x_mye_event: str | None = Header(default=None),
    x_mye_event_id: str | None = Header(default=None),
):
    """Receptor público para testing. Verifica HMAC con TEST_SECRET y guarda."""
    body = await request.body()
    if slow_ms:
        await asyncio.sleep(min(slow_ms / 1000.0, 60))

    # Forced failures
    if fail_until and fail_until > datetime.now(timezone.utc).isoformat():
        from fastapi.responses import JSONResponse
        return JSONResponse({"ok": False, "reason": "fail_until_window"}, 503)
    if fail_rate and random.randint(1, 100) <= fail_rate:
        from fastapi.responses import JSONResponse
        return JSONResponse({"ok": False, "reason": "chaos"}, 500)
    if status_override:
        from fastapi.responses import JSONResponse
        return JSONResponse({"ok": False, "forced": status_override},
                             status_override)

    # Verificar firma (no bloqueante — sólo registramos si falla)
    sig_ok = _verify(body, x_mye_signature or "")
    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except Exception:  # noqa: BLE001
        payload = {"_raw": body.decode("utf-8", errors="replace")[:500]}

    db = get_db()
    rec = {
        "id": new_id(),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "event_id": x_mye_event_id,
        "event_type": x_mye_event,
        "signature_received": x_mye_signature,
        "signature_valid": sig_ok,
        "payload": payload,
        "size_bytes": len(body),
    }
    await db.webhook_test_received.insert_one(rec)
    # Cap circular: borra los más viejos si pasamos CAP
    total = await db.webhook_test_received.count_documents({})
    if total > CAP:
        old = await db.webhook_test_received.find(
            {}, {"_id": 1}, sort=[("received_at", 1)],
        ).limit(total - CAP).to_list(length=total - CAP)
        if old:
            await db.webhook_test_received.delete_many(
                {"_id": {"$in": [o["_id"] for o in old]}},
            )
    rec.pop("_id", None)
    log.info("webhook_test_echo_received", extra={"context": {
        "event_type": x_mye_event, "sig_ok": sig_ok,
        "payload_size": len(body),
    }})
    return ok({"received": True, "signature_valid": sig_ok,
               "event_id": x_mye_event_id, "received_at": rec["received_at"]})


@router.get("/received")
async def list_received(
    limit: int = Query(default=100, ge=1, le=CAP),
    event_type: str | None = Query(default=None),
):
    """Listar eventos recibidos recientemente. Útil para verificar entregas
    durante chaos testing."""
    db = get_db()
    q: dict = {}
    if event_type:
        q["event_type"] = event_type
    cursor = db.webhook_test_received.find(q, {"_id": 0}).sort(
        "received_at", -1,
    ).limit(limit)
    items = await cursor.to_list(length=limit)
    return ok({"items": items, "count": len(items),
               "test_secret_hint": TEST_SECRET[:8] + "…"})


@router.delete("/received")
async def clear_received():
    db = get_db()
    r = await db.webhook_test_received.delete_many({})
    return ok({"cleared": r.deleted_count})
