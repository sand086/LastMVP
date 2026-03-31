"""
Webhook integration system — Plug&Play for external systems.
Supports configurable endpoints, HMAC verification, automatic retries,
and delivery logging.
"""
import asyncio
import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies import db, get_current_user, require_role

logger = logging.getLogger("webhooks")
router = APIRouter(tags=["Webhooks"])

# ─── Available events ─────────────────────────────────────────────
WEBHOOK_EVENTS = {
    "journey.started": "Se dispara cuando una ruta cambia a estado 'in_progress'",
    "journey.closed": "Se dispara cuando una ruta se cierra con sus metricas finales",
    "incident.created": "Se dispara al registrar una nueva incidencia",
    "incident.resolved": "Se dispara al resolver una incidencia",
    "package.status_changed": "Se dispara cuando el status de un paquete cambia",
    "layout.uploaded": "Se dispara al procesar exitosamente un archivo de layout Cosmo",
    "quality.evaluated": "Se dispara al completar evaluacion de calidad IA de una ruta",
}

MAX_RETRIES = 3
RETRY_DELAYS = [5, 30, 120]  # seconds: 5s, 30s, 2min


# ─── Models ────────────────────────────────────────────────────────
class WebhookCreate(BaseModel):
    name: str
    url: str
    events: list[str]
    headers: Optional[dict] = {}
    is_active: Optional[bool] = True


class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    events: Optional[list[str]] = None
    headers: Optional[dict] = None
    is_active: Optional[bool] = None


# ─── CRUD Endpoints ────────────────────────────────────────────────
@router.get("/webhooks/events")
async def list_available_events(user: dict = Depends(get_current_user)):
    """List all available webhook events with descriptions."""
    return {"events": [{"event": k, "description": v} for k, v in WEBHOOK_EVENTS.items()]}


@router.get("/webhooks")
async def list_webhooks(user: dict = Depends(require_role(["developer", "coordinator"]))):
    """List all configured webhooks."""
    webhooks = await db.webhooks.find({}, {"_id": 0}).to_list(100)
    return webhooks


@router.post("/webhooks")
async def create_webhook(data: WebhookCreate, user: dict = Depends(require_role(["developer", "coordinator"]))):
    """Create a new webhook subscription."""
    invalid = [e for e in data.events if e not in WEBHOOK_EVENTS]
    if invalid:
        raise HTTPException(400, f"Eventos invalidos: {invalid}. Disponibles: {list(WEBHOOK_EVENTS.keys())}")

    if not data.url.startswith("https://") and not data.url.startswith("http://"):
        raise HTTPException(400, "La URL debe comenzar con https:// o http://")

    webhook = {
        "id": str(uuid.uuid4()),
        "name": data.name,
        "url": data.url,
        "events": data.events,
        "headers": data.headers or {},
        "secret": hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:32],
        "is_active": data.is_active,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["email"],
        "deliveries_total": 0,
        "deliveries_success": 0,
        "deliveries_failed": 0,
        "last_triggered_at": None,
        "last_status_code": None,
    }
    await db.webhooks.insert_one(webhook)
    webhook.pop("_id", None)
    return webhook


@router.put("/webhooks/{webhook_id}")
async def update_webhook(webhook_id: str, data: WebhookUpdate, user: dict = Depends(require_role(["developer", "coordinator"]))):
    """Update a webhook configuration."""
    update = {k: v for k, v in data.model_dump().items() if v is not None}
    if "events" in update:
        invalid = [e for e in update["events"] if e not in WEBHOOK_EVENTS]
        if invalid:
            raise HTTPException(400, f"Eventos invalidos: {invalid}")

    result = await db.webhooks.update_one({"id": webhook_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(404, "Webhook no encontrado")
    return {"message": "Webhook actualizado"}


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: str, user: dict = Depends(require_role(["developer", "coordinator"]))):
    """Delete a webhook."""
    result = await db.webhooks.delete_one({"id": webhook_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Webhook no encontrado")
    # Clean delivery logs
    await db.webhook_deliveries.delete_many({"webhook_id": webhook_id})
    return {"message": "Webhook eliminado"}


@router.post("/webhooks/{webhook_id}/test")
async def test_webhook(webhook_id: str, user: dict = Depends(require_role(["developer", "coordinator"]))):
    """Send a test payload to verify the webhook is reachable."""
    webhook = await db.webhooks.find_one({"id": webhook_id}, {"_id": 0})
    if not webhook:
        raise HTTPException(404, "Webhook no encontrado")

    test_payload = {
        "event": "webhook.test",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "message": "Este es un evento de prueba desde LastMile OS",
            "webhook_id": webhook_id,
            "webhook_name": webhook["name"],
        },
    }

    result = await _deliver_webhook(webhook, test_payload, is_test=True)
    return result


@router.get("/webhooks/{webhook_id}/deliveries")
async def get_webhook_deliveries(webhook_id: str, limit: int = 20, user: dict = Depends(require_role(["developer", "coordinator"]))):
    """Get delivery log for a specific webhook."""
    deliveries = await db.webhook_deliveries.find(
        {"webhook_id": webhook_id}, {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    return deliveries


@router.post("/webhooks/{webhook_id}/regenerate-secret")
async def regenerate_secret(webhook_id: str, user: dict = Depends(require_role(["developer", "coordinator"]))):
    """Regenerate the HMAC secret for a webhook."""
    new_secret = hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:32]
    result = await db.webhooks.update_one({"id": webhook_id}, {"$set": {"secret": new_secret}})
    if result.matched_count == 0:
        raise HTTPException(404, "Webhook no encontrado")
    return {"secret": new_secret, "message": "Secret regenerado"}


# ─── Delivery Engine ──────────────────────────────────────────────
def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    """Generate HMAC-SHA256 signature for payload verification."""
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


async def _deliver_webhook(webhook: dict, payload: dict, is_test: bool = False) -> dict:
    """Deliver a single webhook with retry logic."""
    import json
    payload_bytes = json.dumps(payload, default=str).encode()
    signature = _sign_payload(payload_bytes, webhook["secret"])

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event": payload.get("event", "unknown"),
        "X-Webhook-Signature": f"sha256={signature}",
        "X-Webhook-Id": webhook["id"],
        "User-Agent": "LastMileOS-Webhook/1.0",
        **(webhook.get("headers") or {}),
    }

    delivery_log = {
        "id": str(uuid.uuid4()),
        "webhook_id": webhook["id"],
        "event": payload.get("event"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "url": webhook["url"],
        "payload_size": len(payload_bytes),
        "is_test": is_test,
        "attempts": [],
        "status": "pending",
    }

    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(webhook["url"], content=payload_bytes, headers=headers)

            delivery_log["attempts"].append({
                "attempt": attempt + 1,
                "status_code": response.status_code,
                "response_time_ms": int(response.elapsed.total_seconds() * 1000),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            if 200 <= response.status_code < 300:
                delivery_log["status"] = "success"
                delivery_log["final_status_code"] = response.status_code
                break
            elif response.status_code >= 400:
                delivery_log["status"] = "failed"
                delivery_log["final_status_code"] = response.status_code
                if response.status_code < 500 and response.status_code != 429:
                    break  # Client error, don't retry

        except Exception as e:
            delivery_log["attempts"].append({
                "attempt": attempt + 1,
                "error": str(e)[:200],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            delivery_log["status"] = "failed"

        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(RETRY_DELAYS[attempt])

    # Save delivery log
    await db.webhook_deliveries.insert_one(delivery_log)
    delivery_log.pop("_id", None)

    # Update webhook stats
    inc_fields = {"deliveries_total": 1}
    if delivery_log["status"] == "success":
        inc_fields["deliveries_success"] = 1
    else:
        inc_fields["deliveries_failed"] = 1

    await db.webhooks.update_one(
        {"id": webhook["id"]},
        {
            "$inc": inc_fields,
            "$set": {
                "last_triggered_at": datetime.now(timezone.utc).isoformat(),
                "last_status_code": delivery_log.get("final_status_code"),
            },
        },
    )

    return delivery_log


# ─── Event Dispatcher (called from other routes) ──────────────────
async def dispatch_webhook_event(event: str, data: dict):
    """Fire-and-forget dispatcher: finds all active webhooks subscribed to
    this event and delivers the payload in background tasks."""
    webhooks = await db.webhooks.find(
        {"is_active": True, "events": event}, {"_id": 0}
    ).to_list(50)

    if not webhooks:
        return

    payload = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }

    for wh in webhooks:
        asyncio.create_task(_deliver_webhook(wh, payload))

    logger.info(f"Webhook event '{event}' dispatched to {len(webhooks)} subscribers")
