"""PROMPT 11 — Notificaciones (email + WhatsApp deeplink + AutomationService).

Cobertura:
  * NotificationService.send_email mockea cuando RESEND_API_KEY está vacío
  * build_wa_deeplink valida E.164 + URL-encodes el texto
  * AutomationService bloquea cuando R03 dice no
  * AutomationService manda email cuando solucion automatizable + permiso allowed
  * AutomationService genera deeplink WA correcto
  * Endpoint /api/admin/notifications/test envía email (mock-mode en CI)
  * Endpoint /api/agent/tickets/{id}/automate ejecuta y registra timeline
"""
from __future__ import annotations
import os
import pytest
from httpx import AsyncClient, ASGITransport

from server import app
from core.security import create_access_token
from core.uuid import new_id


def _bearer(*, user_id, tenant_id, role="agent", email="agent@test.local"):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_id, tenant_id=tenant_id, role=role, email=email)}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def notif_setup(db, monkeypatch):
    """Tenant + admin/agent + cliente con ops contacts + motivo + solucion + permiso."""
    monkeypatch.setenv("RESEND_API_KEY", "")  # forzamos mock en tests
    tid = new_id()
    uid_admin, uid_agent = new_id(), new_id()
    pj_id, cl_id, motivo_id, sol_id, guia_id, ticket_id = (new_id() for _ in range(6))

    await db.tenants.insert_one({"id": tid, "slug": "n11", "name": "N11", "status": "active"})
    await db.users.insert_many([
        {"id": uid_admin, "tenant_id": tid, "email": "ad@t",
         "password_hash": "x", "name": "Admin", "role": "admin", "status": "active"},
        {"id": uid_agent, "tenant_id": tid, "email": "ag@t",
         "password_hash": "x", "name": "Agente", "role": "agent", "status": "active"},
    ])
    await db.projects.insert_one({"id": pj_id, "tenant_id": tid, "name": "P", "status": "active"})
    await db.clients.insert_one({
        "id": cl_id, "tenant_id": tid, "project_id": pj_id, "name": "Cliente Test",
        "ingest_mode": "webhook", "webhook_token": "wh-secret",
        "ops_contact_name": "Ops Lead", "ops_contact_email": "ops@cliente.test",
        "ops_contact_wa": "+5215551234567",
    })
    await db.motivos.insert_one({
        "id": motivo_id, "tenant_id": tid, "name": "Excepción de dirección",
        "active": True, "restricted": False,
    })
    await db.soluciones.insert_one({
        "id": sol_id, "tenant_id": tid, "motivo_id": motivo_id,
        "nombre": "Confirmar dirección con cliente",
        "template_msg": "Por favor confirma la dirección de entrega del envío.",
        "automatable": True, "active": True,
    })
    await db.guias.insert_one({
        "id": guia_id, "tenant_id": tid, "tracking_id": "FX-NOT-1",
        "carrier_id": "fedex", "client_id": cl_id,
        "carrier_status": "exception", "internal_status": "in_transit",
        "is_terminal": False,
    })
    await db.tickets.insert_one({
        "id": ticket_id, "tenant_id": tid, "client_id": cl_id, "guia_id": guia_id,
        "carrier_id": "fedex", "status": "in_progress",
        "assigned_agent_id": uid_agent,
        "incident_type": "address_issue", "canonical_status": "exception",
        "carrier_status_raw": "ADDRESS_ISSUE", "source": "ingest",
        "solucion_id": sol_id,
        "created_at": "2026-05-01T00:00:00Z", "updated_at": "2026-05-01T00:00:00Z",
    })
    return {
        "tenant_id": tid, "admin_id": uid_admin, "agent_id": uid_agent,
        "client_id": cl_id, "motivo_id": motivo_id, "solucion_id": sol_id,
        "ticket_id": ticket_id,
    }


# ──────────────────────── WhatsApp deeplink ───────────────────────────
def test_wa_deeplink_valid_phone():
    from core.whatsapp import build_wa_deeplink
    url = build_wa_deeplink("+52 (155) 5123-4567", "Hola Juan & Mar")
    assert url.startswith("https://wa.me/5215551234567?text=")
    # ampersand y espacios deben quedar URL-encoded
    assert "Hola%20Juan%20%26%20Mar" in url


def test_wa_deeplink_invalid_phone():
    from core.whatsapp import build_wa_deeplink
    with pytest.raises(ValueError):
        build_wa_deeplink("not-a-phone", "x")


# ──────────────────────── send_email mock ─────────────────────────────
@pytest.mark.asyncio
async def test_send_email_mock_when_key_empty(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "")
    from services.notification_service import send_email
    res = await send_email(to="x@y.com", subject="t", html="<p>hola</p>")
    assert res.ok is True
    assert res.mock is True
    assert res.id and res.id.startswith("mock_")


# ──────────────────────── AutomationService blocks ────────────────────
@pytest.mark.asyncio
async def test_automation_blocked_when_no_permission(notif_setup, db):
    s = notif_setup
    # No insertamos automation_permissions → default deny
    from services.automation_service import AutomationService
    svc = AutomationService(tenant_id=s["tenant_id"], actor_id=s["agent_id"])
    out = await svc.execute_for_ticket(s["ticket_id"], channel="email")
    assert out.executed is False
    assert out.reason == "permission_denied"


@pytest.mark.asyncio
async def test_automation_executes_email_when_allowed(notif_setup, db):
    s = notif_setup
    await db.automation_permissions.insert_one({
        "id": new_id(), "tenant_id": s["tenant_id"], "client_id": s["client_id"],
        "solucion_id": s["solucion_id"], "channel": "email", "allowed": True,
    })
    from services.automation_service import AutomationService
    svc = AutomationService(tenant_id=s["tenant_id"], actor_id=s["agent_id"])
    out = await svc.execute_for_ticket(s["ticket_id"], channel="email")
    assert out.executed is True
    assert out.reason == "ok"
    assert out.artifact["email_id"]
    assert out.artifact["mock"] is True
    assert out.artifact["to"] == "ops@cliente.test"
    # Timeline: automation_executed registrado
    tl = await db.timeline_events.find(
        {"tenant_id": s["tenant_id"], "ticket_id": s["ticket_id"],
         "event_type": "automation_executed"}, {"_id": 0},
    ).to_list(5)
    assert tl and tl[0]["payload"]["ok"] is True
    assert tl[0]["payload"]["channel"] == "email"


@pytest.mark.asyncio
async def test_automation_whatsapp_returns_deeplink(notif_setup, db):
    s = notif_setup
    await db.automation_permissions.insert_one({
        "id": new_id(), "tenant_id": s["tenant_id"], "client_id": s["client_id"],
        "solucion_id": s["solucion_id"], "channel": "whatsapp", "allowed": True,
    })
    from services.automation_service import AutomationService
    svc = AutomationService(tenant_id=s["tenant_id"], actor_id=s["agent_id"])
    out = await svc.execute_for_ticket(s["ticket_id"], channel="whatsapp")
    assert out.executed is True
    assert out.artifact["deeplink"].startswith("https://wa.me/5215551234567?text=")


@pytest.mark.asyncio
async def test_automation_motivo_restricted_blocks(notif_setup, db):
    s = notif_setup
    await db.motivos.update_one({"id": s["motivo_id"]}, {"$set": {"restricted": True}})
    await db.automation_permissions.insert_one({
        "id": new_id(), "tenant_id": s["tenant_id"], "client_id": s["client_id"],
        "solucion_id": s["solucion_id"], "channel": "email", "allowed": True,
    })
    from services.automation_service import AutomationService
    svc = AutomationService(tenant_id=s["tenant_id"], actor_id=s["agent_id"])
    out = await svc.execute_for_ticket(s["ticket_id"], channel="email")
    assert out.executed is False
    assert out.reason == "motivo_restricted"


# ──────────────────────── Admin /test endpoint ────────────────────────
@pytest.mark.asyncio
async def test_admin_notifications_test_endpoint(http_client, notif_setup):
    s = notif_setup
    h = _bearer(user_id=s["admin_id"], tenant_id=s["tenant_id"], role="admin")
    r = await http_client.post("/api/admin/notifications/test",
                                json={"to": "demo@example.com"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["to"] == "demo@example.com"
    assert body["result"]["ok"] is True
    assert body["result"]["mock"] is True


@pytest.mark.asyncio
async def test_admin_notifications_config_hides_secret(http_client, notif_setup):
    s = notif_setup
    h = _bearer(user_id=s["admin_id"], tenant_id=s["tenant_id"], role="admin")
    r = await http_client.get("/api/admin/notifications/config", headers=h)
    body = r.json()["data"]
    assert "sender_email" in body
    assert "resend_configured" in body
    # Nunca el endpoint expone la API key
    assert "api_key" not in str(body).lower()


# ──────────────────────── Agent endpoint executes ─────────────────────
@pytest.mark.asyncio
async def test_agent_automate_endpoint_executes(http_client, db, notif_setup):
    s = notif_setup
    await db.automation_permissions.insert_one({
        "id": new_id(), "tenant_id": s["tenant_id"], "client_id": s["client_id"],
        "solucion_id": s["solucion_id"], "channel": "email", "allowed": True,
    })
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.post(f"/api/agent/tickets/{s['ticket_id']}/automate",
                                json={"channel": "email"}, headers=h)
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["can_automate"] is True
    assert body["executed"] is True
    assert body["channel"] == "email"
