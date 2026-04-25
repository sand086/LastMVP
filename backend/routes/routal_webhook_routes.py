"""
Routal webhook receiver — multi-tenant (R00A.5).

URL pattern: POST /api/webhooks/routal/{client_id}
HMAC-SHA256 signature: header X-Routal-Signature (hex)
Idempotency: by event_id (header X-Routal-Event-Id or payload.id)
"""
import asyncio
import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends
from starlette.responses import JSONResponse

from dependencies import get_current_user, db
from utils.encryption import decrypt_credentials
from workers.routal_event_processor import process_routal_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")


def _verify_hmac(secret: str, body: bytes, signature: str) -> bool:
    if not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    # Constant-time compare; tolerate optional 'sha256=' prefix
    candidate = signature.removeprefix("sha256=").strip()
    return hmac.compare_digest(expected, candidate)


@router.post("/routal/{client_id}")
async def receive_routal_event(client_id: str, request: Request):
    integ = await db.client_integrations.find_one(
        {"client_id": client_id, "integration_type": "routal", "status": "active"},
        {"_id": 0, "credentials_encrypted": 1, "client_id": 1},
    )
    if not integ:
        raise HTTPException(status_code=404, detail="Integración no encontrada o inactiva")

    body = await request.body()
    creds = decrypt_credentials(integ.get("credentials_encrypted") or "")
    secret = creds.get("routal_webhook_secret")

    if secret:
        sig = request.headers.get("X-Routal-Signature", "")
        if not _verify_hmac(secret, body, sig):
            logger.warning(f"[routal-webhook] invalid signature for client {client_id}")
            raise HTTPException(status_code=401, detail="Firma inválida")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Body no es JSON válido")

    event_id = (
        request.headers.get("X-Routal-Event-Id")
        or payload.get("event_id")
        or payload.get("id")
    )
    event_type = payload.get("event") or payload.get("type") or payload.get("event_type") or "unknown"

    if not event_id:
        raise HTTPException(status_code=400, detail="event_id requerido")

    # Idempotencia
    existing = await db.routal_events.find_one(
        {"event_id": event_id, "client_id": client_id},
        {"_id": 0, "processed": 1},
    )
    if existing:
        return {"ok": True, "duplicate": True, "processed": existing.get("processed", False)}

    # Save
    await db.routal_events.insert_one({
        "event_id": event_id,
        "client_id": client_id,
        "event_type": event_type,
        "payload": payload,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "processed": False,
        "attempts": 0,
    })

    # Fire-and-forget processing (200 OK in <500ms)
    asyncio.create_task(process_routal_event(db, event_id, client_id))

    return {"ok": True, "event_id": event_id}


@router.get("/routal/{client_id}/status")
async def webhook_status(client_id: str, user: dict = Depends(get_current_user)):
    if user.get("role") not in ("developer", "coordinator"):
        raise HTTPException(status_code=403, detail="Acceso restringido")

    pending = await db.routal_events.count_documents({"client_id": client_id, "processed": False})
    failed = await db.routal_events.count_documents({"client_id": client_id, "error": {"$exists": True, "$ne": None}})
    last = await db.routal_events.find_one(
        {"client_id": client_id},
        {"_id": 0, "received_at": 1},
        sort=[("received_at", -1)],
    )
    base = PUBLIC_BASE_URL or str(_default_base_url())
    return {
        "pending": pending,
        "failed": failed,
        "last_event_at": last.get("received_at") if last else None,
        "webhook_url": f"{base}/api/webhooks/routal/{client_id}",
    }


def _default_base_url():
    """Fallback al hostname del request si PUBLIC_BASE_URL no está set.
    En prod el usuario debe poner PUBLIC_BASE_URL en .env."""
    return os.environ.get("REACT_APP_BACKEND_URL", "https://lastmile-mvp.preview.emergentagent.com")
