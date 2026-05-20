"""Routes WhatsApp / Zenvia (PROMPT 21) — bidireccional.

Outbound:
  POST /api/admin/whatsapp/send            admin+

Inbound webhook:
  POST /api/webhooks/zenvia/inbound        público (verifica HMAC SHA-256)

Lectura de conversaciones:
  GET  /api/tickets/{ticket_id}/whatsapp   agent+
"""
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.db import get_db
from core.response import fail, ok
from core.uuid import new_id
from middleware.rbac import require_min_role
from services import zenvia


router_admin = APIRouter(prefix="/api/admin/whatsapp", tags=["whatsapp"])
router_webhook = APIRouter(prefix="/api/webhooks/zenvia", tags=["whatsapp-webhook"])
router_public = APIRouter(prefix="/api", tags=["whatsapp"])

_ADMIN_RBAC = require_min_role("admin")
_AGENT_RBAC = require_min_role("agent")


class SendBody(BaseModel):
    to: str = Field(min_length=8, max_length=20, pattern=r"^\+\d{8,18}$")
    text: str = Field(min_length=1, max_length=4096)
    ticket_id: str | None = None


@router_admin.post("/send")
async def send_whatsapp(body: SendBody, request: Request, _: object = Depends(_ADMIN_RBAC)):
    user = request.state.user
    db = get_db()
    try:
        res = await zenvia.send_text(to=body.to, text=body.text)
    except zenvia.ZenviaError as e:
        return fail("INTEGRATION_ERROR", str(e), field=None)
    except ValueError as e:
        return fail("VALIDATION_FAILED", str(e), field="to")

    msg_doc = {
        "id": new_id(), "tenant_id": user.tenant_id,
        "ticket_id": body.ticket_id,
        "direction": "outbound",
        "from": "myexcellence", "to": body.to,
        "text": body.text, "media_url": None, "media_type": None,
        "provider": "zenvia",
        "provider_id": res.get("id", ""),
        "status": res.get("status") or "queued",
        "mocked": bool(res.get("mocked")),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user.id,
    }
    await db.whatsapp_messages.insert_one(dict(msg_doc))
    msg_doc.pop("_id", None)
    return ok(msg_doc)


@router_webhook.post("/inbound")
async def zenvia_inbound(request: Request):
    """Recepción de mensajes y status updates de Zenvia.

    Verifica HMAC SHA-256 contra `ZENVIA_WEBHOOK_SECRET` (fallback `ZENVIA_API_KEY`).
    """
    raw = await request.body()
    sig = request.headers.get("X-Zenvia-Signature", "")
    if not zenvia.verify_signature(raw, sig):
        raise HTTPException(status_code=401, detail="invalid signature")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")
    parsed = zenvia.parse_inbound(payload)
    db = get_db()
    inserted = 0
    for m in parsed["messages"]:
        # Buscar ticket por número del cliente (cross-tenant: el routing sube a quien tenga el cliente)
        client = await db.clients.find_one({
            "$or": [{"phone": m["from"]}, {"whatsapp_number": m["from"]}],
        }, {"_id": 0, "id": 1, "tenant_id": 1})
        ticket_id = None
        tenant_id = (client or {}).get("tenant_id")
        if tenant_id:
            # Latest open ticket del cliente
            t = await db.tickets.find_one(
                {"client_id": client["id"], "tenant_id": tenant_id,
                 "is_terminal": {"$ne": True}},
                {"_id": 0, "id": 1}, sort=[("created_at", -1)],
            )
            ticket_id = (t or {}).get("id")
        await db.whatsapp_messages.insert_one({
            "id": new_id(), "tenant_id": tenant_id,
            "ticket_id": ticket_id,
            "direction": "inbound",
            "from": m["from"], "to": m["to"],
            "text": m["text"], "media_url": m["media_url"], "media_type": m["media_type"],
            "provider": "zenvia", "provider_id": m["provider_id"],
            "status": "received",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "raw_ts": m["ts"],
        })
        inserted += 1
    # Statuses (delivered/read/etc.)
    for s in parsed["statuses"]:
        await db.whatsapp_messages.update_many(
            {"provider_id": s["provider_id"]},
            {"$set": {"status": s["status"],
                      "status_updated_at": datetime.now(timezone.utc).isoformat()}},
        )
    return {"received": True, "messages": inserted, "statuses": len(parsed["statuses"])}


@router_public.get("/tickets/{ticket_id}/whatsapp")
async def conversation(ticket_id: str, request: Request, _: object = Depends(_AGENT_RBAC)):
    user = request.state.user
    db = get_db()
    cursor = db.whatsapp_messages.find(
        {"tenant_id": user.tenant_id, "ticket_id": ticket_id},
        {"_id": 0},
    ).sort("created_at", 1).limit(500)
    items = [m async for m in cursor]
    return ok({"items": items, "count": len(items)})
