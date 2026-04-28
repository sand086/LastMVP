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
        {"_id": 0, "credentials_encrypted": 1, "client_id": 1, "branches": 1},
    )
    if not integ:
        raise HTTPException(
            status_code=404,
            detail=(
                "Integración Routal no encontrada o inactiva para este client_id. "
                "Verifica en /settings → Integraciones que existe un registro "
                "type=routal y status=active. Si acabas de crearlo, recarga e inténtalo de nuevo."
            ),
        )

    body = await request.body()

    # Try to peek at payload's project_id for multi-branch routing (RT-01).
    # If found, use the branch's own webhook_secret + tag the event with branch_id.
    payload_peek = None
    if body:
        try:
            payload_peek = await request.json()
        except Exception:
            payload_peek = None

    branch_id = None
    branch_secret = None
    project_id_in_payload = None
    if payload_peek and isinstance(payload_peek, dict):
        project_id_in_payload = (
            payload_peek.get("project_id")
            or payload_peek.get("organization_id")
            or (payload_peek.get("plan") or {}).get("project_id")
            or (payload_peek.get("data") or {}).get("project_id")
        )
    if project_id_in_payload:
        branches = integ.get("branches") or {}
        for bid, entry in branches.items():
            if not entry.get("active", True):
                continue
            enc = entry.get("credentials_encrypted") or ""
            if not enc:
                continue
            b_creds = decrypt_credentials(enc)
            if b_creds.get("routal_project_id") == project_id_in_payload:
                branch_id = bid
                branch_secret = b_creds.get("routal_webhook_secret")
                break

    # HMAC: prefer branch secret if we matched a branch; else fall back to top-level
    if branch_secret is not None:
        secret = branch_secret
    else:
        creds = decrypt_credentials(integ.get("credentials_encrypted") or "")
        secret = creds.get("routal_webhook_secret")

    if secret:
        sig = (
            request.headers.get("X-Routal-Signature")
            or request.headers.get("X-Webhook-Signature")
            or request.headers.get("X-Hub-Signature-256")
            or ""
        )
        if not _verify_hmac(secret, body, sig):
            logger.warning(f"[routal-webhook] invalid signature for client {client_id} branch={branch_id}")
            raise HTTPException(status_code=401, detail="Firma inválida")

    # Empty body is acceptable for "test webhook" pings — return 200 so the
    # integrator's UI shows success.
    if not body:
        return {"ok": True, "test": True, "note": "empty body accepted as healthcheck"}

    if payload_peek is None:
        raise HTTPException(status_code=400, detail="Body no es JSON válido")
    payload = payload_peek

    event_id = (
        request.headers.get("X-Routal-Event-Id")
        or payload.get("event_id")
        or payload.get("id")
    )
    event_type = payload.get("event") or payload.get("type") or payload.get("event_type") or "unknown"

    if not event_id:
        if event_type in ("test", "ping", "unknown") or payload.get("test") is True:
            logger.info(f"[routal-webhook] test ping received for client {client_id} branch={branch_id}")
            return {"ok": True, "test": True, "note": "no event_id; treated as test ping"}
        raise HTTPException(status_code=400, detail="event_id requerido")

    existing = await db.routal_events.find_one(
        {"event_id": event_id, "client_id": client_id},
        {"_id": 0, "processed": 1},
    )
    if existing:
        return {"ok": True, "duplicate": True, "processed": existing.get("processed", False)}

    await db.routal_events.insert_one({
        "event_id": event_id,
        "client_id": client_id,
        "branch_id": branch_id,
        "event_type": event_type,
        "payload": payload,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "processed": False,
        "attempts": 0,
    })

    asyncio.create_task(process_routal_event(db, event_id, client_id))

    return {"ok": True, "event_id": event_id, "branch_id": branch_id}


@router.get("/routal/{client_id}")
async def receive_routal_event_healthcheck(client_id: str):
    """Public GET handler. Many SaaS dashboards (Routal included) hit GET on the
    webhook URL to verify it exists and is reachable BEFORE sending a POST test.
    Returns 200 with metadata so the dashboard shows the URL as 'reachable'.
    """
    integ = await db.client_integrations.find_one(
        {"client_id": client_id, "integration_type": "routal"},
        {"_id": 0, "status": 1},
    )
    return {
        "service": "lastmile-os",
        "endpoint": "routal-webhook-receiver",
        "client_id": client_id,
        "integration_active": bool(integ and integ.get("status") == "active"),
        "expected_method": "POST",
        "expected_signature_header": "X-Routal-Signature",
        "note": "Send POST with JSON body and HMAC-SHA256 signature (hex) over the raw body.",
    }


@router.options("/routal/{client_id}")
async def receive_routal_event_preflight(client_id: str):
    """Explicit OPTIONS handler for CORS preflight. Returns 200 with empty body
    so external dashboards (Routal) don't get 405 when their browser sends a
    preflight before the actual POST.
    """
    return JSONResponse(content={}, status_code=200)


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
