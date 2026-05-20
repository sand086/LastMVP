"""Iter23 — POST /api/agent/guias/{guia_id}/cancel
=====================================================

Cierra el loop outbound 1:1 sobre Routal:
  * Recibe `project_id` opcional en el body; si no se pasa, lo toma de
    `guia.carrier_meta.routal_project_id` (multi-proyecto Cubbo).
  * Llama `RoutalAdapter.send_instruction({status:'canceled', project_id:X})`.
  * Persiste `timeline_events` (carrier_outbound_sent) en el ticket asociado.
  * Actualiza `guia.outbound_last_*` para auditoría/idempotencia.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id
from repositories.clients import ClientRepository
from services.cae.interface import ApiResponse
from services.cae.adapters.routal import RoutalAdapter


def _bearer(*, user_id, tenant_id, role="agent"):
    tok = create_access_token(user_id=user_id, tenant_id=tenant_id,
                              role=role, email=f"{user_id[:6]}@t")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def env(db):
    tid = new_id()
    other_tid = new_id()
    agent_id = new_id()
    other_agent_id = new_id()
    project_id = new_id()
    client_id = new_id()
    ticket_id = new_id()
    guia_id = new_id()
    await db.tenants.insert_many([
        {"id": tid, "slug": "cubbo", "name": "Cubbo", "status": "active"},
        {"id": other_tid, "slug": "other", "name": "Other", "status": "active"},
    ])
    await db.users.insert_many([
        {"id": agent_id, "tenant_id": tid, "email": "a@cubbo",
         "role": "agent", "status": "active"},
        {"id": other_agent_id, "tenant_id": other_tid, "email": "a@other",
         "role": "agent", "status": "active"},
    ])
    await db.projects.insert_one({"id": project_id, "tenant_id": tid,
                                    "name": "P", "status": "active"})
    await db.clients.insert_one({
        "id": client_id, "tenant_id": tid, "project_id": project_id,
        "name": "Cubbo", "ingest_mode": "pulling",
        "preferred_carrier_code": "routal", "carriers": {},
    })
    # Persist Routal config on client (cifrado Fernet via repo)
    repo = ClientRepository(tenant_id=tid)
    await repo.set_carrier_config(client_id, "routal", {
        "api_key": "K-CUBBO",
        "project_ids": ["proj-north", "proj-south"],
        "default_project_id": "proj-north",
    })
    # A guía ingested by north project
    await db.guias.insert_one({
        "id": guia_id, "tenant_id": tid, "client_id": client_id,
        "tracking_id": "TRK-CANCEL-1", "carrier_code": "routal",
        "carrier_status": "in_transit",
        "internal_status": "in_transit", "is_terminal": False,
        "carrier_meta": {"routal_project_id": "proj-south",
                          "plan_id": "plan-99"},
    })
    # Linked ticket
    await db.tickets.insert_one({
        "id": ticket_id, "tenant_id": tid, "client_id": client_id,
        "guia_id": guia_id, "tracking_id": "TRK-CANCEL-1",
        "status": "in_progress", "priority": "P2",
    })
    return {
        "tid": tid, "other_tid": other_tid,
        "agent": agent_id, "other_agent": other_agent_id,
        "client_id": client_id, "guia_id": guia_id, "ticket_id": ticket_id,
    }


# ─── 1) Happy path ─────────────────────────────────────────────────────
class TestCancelHappyPath:
    async def test_uses_carrier_meta_project_id_by_default(self, env, http_client,
                                                              db, monkeypatch):
        """Sin payload.project_id, el endpoint debe tomar el routal_project_id
        que se persistió cuando la guía fue ingestada (proj-south)."""
        called: dict = {}

        async def fake_send(self, tracking_id, payload):
            called["tracking_id"] = tracking_id
            called["payload"] = dict(payload or {})
            return ApiResponse(received=True, status=200,
                               fallback_to_email=False)

        monkeypatch.setattr(RoutalAdapter, "send_instruction", fake_send)
        h = _bearer(user_id=env["agent"], tenant_id=env["tid"])
        r = await http_client.post(
            f"/api/agent/guias/{env['guia_id']}/cancel",
            headers=h, json={"comments": "Cliente solicitó cancelación"})
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["received"] is True
        assert body["project_id"] == "proj-south"  # from carrier_meta
        assert body["carrier_code"] == "routal"
        assert body["tracking_id"] == "TRK-CANCEL-1"

        # Adapter received the right project_id
        assert called["tracking_id"] == "TRK-CANCEL-1"
        assert called["payload"]["status"] == "canceled"
        assert called["payload"]["project_id"] == "proj-south"
        assert called["payload"]["comments"] == "Cliente solicitó cancelación"

    async def test_payload_project_id_overrides_carrier_meta(self, env,
                                                                http_client,
                                                                monkeypatch):
        """`payload.project_id` debe ganar sobre el persistido en carrier_meta
        — útil si el agente sabe que el stop migró de proyecto."""
        called: dict = {}

        async def fake_send(self, tracking_id, payload):
            called["payload"] = dict(payload or {})
            return ApiResponse(received=True, status=200)

        monkeypatch.setattr(RoutalAdapter, "send_instruction", fake_send)
        h = _bearer(user_id=env["agent"], tenant_id=env["tid"])
        r = await http_client.post(
            f"/api/agent/guias/{env['guia_id']}/cancel",
            headers=h, json={"project_id": "proj-north"})
        assert r.status_code == 200
        assert called["payload"]["project_id"] == "proj-north"
        assert r.json()["data"]["project_id"] == "proj-north"

    async def test_appends_timeline_event_on_ticket(self, env, http_client,
                                                      db, monkeypatch):
        async def fake_send(self, tracking_id, payload):
            return ApiResponse(received=True, status=200)
        monkeypatch.setattr(RoutalAdapter, "send_instruction", fake_send)

        h = _bearer(user_id=env["agent"], tenant_id=env["tid"])
        await http_client.post(
            f"/api/agent/guias/{env['guia_id']}/cancel",
            headers=h, json={"comments": "auditable"})

        events = await db.timeline_events.find(
            {"tenant_id": env["tid"], "ticket_id": env["ticket_id"]},
            {"_id": 0}).to_list(None)
        outbound = [e for e in events
                    if e["event_type"] == "carrier_outbound_sent"]
        assert len(outbound) == 1
        ev = outbound[0]
        assert ev["payload"]["carrier_code"] == "routal"
        assert ev["payload"]["project_id"] == "proj-south"
        assert ev["payload"]["received"] is True
        assert ev["payload"]["outbound_status"] == "canceled"
        assert "Cancelación enviada a routal" in ev["description"]
        assert ev["actor_id"] == env["agent"]

    async def test_persists_outbound_audit_on_guia(self, env, http_client,
                                                     db, monkeypatch):
        async def fake_send(self, tracking_id, payload):
            return ApiResponse(received=True, status=200)
        monkeypatch.setattr(RoutalAdapter, "send_instruction", fake_send)

        h = _bearer(user_id=env["agent"], tenant_id=env["tid"])
        await http_client.post(f"/api/agent/guias/{env['guia_id']}/cancel",
                                headers=h, json={})

        g = await db.guias.find_one({"id": env["guia_id"]}, {"_id": 0})
        assert g["outbound_last_action"] == "cancel"
        assert g["outbound_last_status"] == "received"
        assert g["outbound_last_http"] == 200
        assert g["outbound_last_at"]


# ─── 2) Adapter failure flows ─────────────────────────────────────────
class TestCancelFailures:
    async def test_carrier_failure_marks_guia_failed(self, env, http_client,
                                                       db, monkeypatch):
        async def fake_send(self, tracking_id, payload):
            return ApiResponse(received=False, status=502,
                               fallback_to_email=True)
        monkeypatch.setattr(RoutalAdapter, "send_instruction", fake_send)

        h = _bearer(user_id=env["agent"], tenant_id=env["tid"])
        r = await http_client.post(f"/api/agent/guias/{env['guia_id']}/cancel",
                                     headers=h, json={})
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["received"] is False
        assert body["status"] == 502
        assert body["fallback_to_email"] is True
        g = await db.guias.find_one({"id": env["guia_id"]}, {"_id": 0})
        assert g["outbound_last_status"] == "failed"

    async def test_client_without_carrier_config_400(self, env, http_client, db):
        """Si el cliente no tiene Routal configurado, debe responder 400."""
        # New guía on a fresh client WITHOUT carrier config
        other_client_id = new_id()
        other_guia_id = new_id()
        await db.clients.insert_one({
            "id": other_client_id, "tenant_id": env["tid"],
            "name": "no-config", "ingest_mode": "webhook", "carriers": {},
        })
        await db.guias.insert_one({
            "id": other_guia_id, "tenant_id": env["tid"],
            "client_id": other_client_id, "tracking_id": "TRK-X",
            "carrier_code": "routal", "carrier_meta": {},
        })
        h = _bearer(user_id=env["agent"], tenant_id=env["tid"])
        r = await http_client.post(f"/api/agent/guias/{other_guia_id}/cancel",
                                     headers=h, json={})
        assert r.status_code in (400, 422)


# ─── 3) Security: RBAC + cross-tenant ─────────────────────────────────
class TestCancelSecurity:
    async def test_cross_tenant_guia_404(self, env, http_client):
        """Agent del tenant B no debe poder cancelar una guía del tenant A."""
        h = _bearer(user_id=env["other_agent"], tenant_id=env["other_tid"])
        r = await http_client.post(f"/api/agent/guias/{env['guia_id']}/cancel",
                                     headers=h, json={})
        assert r.status_code == 404

    async def test_no_auth_401(self, env, http_client):
        r = await http_client.post(f"/api/agent/guias/{env['guia_id']}/cancel",
                                     json={})
        assert r.status_code == 401

    async def test_viewer_role_forbidden(self, env, http_client, db):
        viewer_id = new_id()
        await db.users.insert_one({"id": viewer_id, "tenant_id": env["tid"],
                                     "email": "v@t", "role": "client_viewer",
                                     "status": "active"})
        h = _bearer(user_id=viewer_id, tenant_id=env["tid"],
                    role="client_viewer")
        r = await http_client.post(f"/api/agent/guias/{env['guia_id']}/cancel",
                                     headers=h, json={})
        assert r.status_code == 403


# ─── 4) Edge cases ─────────────────────────────────────────────────────
class TestCancelEdges:
    async def test_unknown_guia_404(self, env, http_client):
        h = _bearer(user_id=env["agent"], tenant_id=env["tid"])
        r = await http_client.post(f"/api/agent/guias/{new_id()}/cancel",
                                     headers=h, json={})
        assert r.status_code == 404

    async def test_no_linked_ticket_still_succeeds(self, env, http_client,
                                                     db, monkeypatch):
        """Si la guía no tiene ticket asociado, el outbound debe enviarse igual
        y solo se omite el insert al timeline (no falla)."""
        loose_guia_id = new_id()
        await db.guias.insert_one({
            "id": loose_guia_id, "tenant_id": env["tid"],
            "client_id": env["client_id"], "tracking_id": "TRK-NO-TKT",
            "carrier_code": "routal",
            "carrier_meta": {"routal_project_id": "proj-north"},
        })

        async def fake_send(self, tracking_id, payload):
            return ApiResponse(received=True, status=200)
        monkeypatch.setattr(RoutalAdapter, "send_instruction", fake_send)

        h = _bearer(user_id=env["agent"], tenant_id=env["tid"])
        r = await http_client.post(f"/api/agent/guias/{loose_guia_id}/cancel",
                                     headers=h, json={})
        assert r.status_code == 200
        assert r.json()["data"]["received"] is True
        # No timeline_events should have been created against this guía
        # since there's no ticket
        count = await db.timeline_events.count_documents({
            "tenant_id": env["tid"],
            "payload.tracking_id": "TRK-NO-TKT",
        })
        assert count == 0
