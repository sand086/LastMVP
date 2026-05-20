"""Tests para PROMPT 21 (Zenvia WhatsApp), PROMPT 22 (Heatmap), PROMPT 23 (Bulk + PDF)."""
from __future__ import annotations
import hashlib
import hmac
import json
import zipfile
import io

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id
from services import zenvia as zenvia_mod
from services import geocoding as geo_mod


def _bearer(*, user_id, tenant_id, role="admin"):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_id, tenant_id=tenant_id, role=role, email='u@t')}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def setup_basic(db):
    tid = new_id()
    uid_admin, uid_agent, uid_target = new_id(), new_id(), new_id()
    cl_id = new_id()
    car_id = new_id()
    await db.tenants.insert_one({"id": tid, "slug": "p21", "name": "P21",
                                 "status": "active"})
    await db.users.insert_many([
        {"id": uid_admin, "tenant_id": tid, "email": "ad@t",
         "role": "admin", "status": "active"},
        {"id": uid_agent, "tenant_id": tid, "email": "ag@t",
         "role": "agent", "status": "active"},
        {"id": uid_target, "tenant_id": tid, "email": "tg@t",
         "role": "agent", "status": "active"},
    ])
    await db.clients.insert_one({
        "id": cl_id, "tenant_id": tid, "name": "Cl P21",
        "phone": "+5215512345678", "whatsapp_number": "+5215512345678",
    })
    await db.carriers.insert_one({
        "id": car_id, "tenant_id": tid, "code": "estafeta", "name": "Estafeta",
    })
    return {"tenant_id": tid, "admin_id": uid_admin, "agent_id": uid_agent,
            "target_agent_id": uid_target, "client_id": cl_id, "carrier_id": car_id}


# ═══════════════════════════ PROMPT 21 — Zenvia ══════════════════════════
class TestZenviaSend:
    async def test_send_text_no_api_key_returns_mocked(self, monkeypatch):
        monkeypatch.delenv("ZENVIA_API_KEY", raising=False)
        res = await zenvia_mod.send_text(to="+5215512345678", text="Hola")
        assert res["mocked"] is True
        assert res["status"] == "MOCKED"

    async def test_send_text_invalid_e164(self):
        with pytest.raises(ValueError):
            await zenvia_mod.send_text(to="5215512345678", text="x")

    async def test_send_endpoint_persists_outbound(self, setup_basic, http_client, monkeypatch, db):
        monkeypatch.delenv("ZENVIA_API_KEY", raising=False)  # forzar mock
        headers = _bearer(user_id=setup_basic["admin_id"], tenant_id=setup_basic["tenant_id"])
        r = await http_client.post(
            "/api/admin/whatsapp/send",
            json={"to": "+5215512345678", "text": "Bienvenido", "ticket_id": None},
            headers=headers,
        )
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["direction"] == "outbound"
        assert d["mocked"] is True
        # Persistido
        m = await db.whatsapp_messages.find_one({"id": d["id"]}, {"_id": 0})
        assert m and m["text"] == "Bienvenido"


class TestZenviaInboundWebhook:
    def test_verify_signature_valid(self, monkeypatch):
        secret = "test-secret"
        monkeypatch.setenv("ZENVIA_WEBHOOK_SECRET", secret)
        body = b'{"hello":"world"}'
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert zenvia_mod.verify_signature(body, sig) is True

    def test_verify_signature_invalid(self, monkeypatch):
        monkeypatch.setenv("ZENVIA_WEBHOOK_SECRET", "test-secret")
        body = b'{"hello":"world"}'
        bad_sig = "sha256=deadbeef"
        assert zenvia_mod.verify_signature(body, bad_sig) is False

    def test_parse_inbound_normalizes_payload(self):
        zenvia_payload = {
            "messages": [{
                "id": "msg-123", "from": "+5215512345678",
                "to": "myexcellence-bot", "timestamp": "2026-05-09T10:00:00Z",
                "contents": [{"type": "text", "text": "Mi paquete no llegó"}],
            }],
            "message_statuses": [
                {"id": "msg-122", "status": "delivered", "timestamp": "2026-05-09T09:55:00Z"},
            ],
        }
        out = zenvia_mod.parse_inbound(zenvia_payload)
        assert len(out["messages"]) == 1
        assert out["messages"][0]["text"] == "Mi paquete no llegó"
        assert out["messages"][0]["from"] == "+5215512345678"
        assert len(out["statuses"]) == 1
        assert out["statuses"][0]["status"] == "delivered"

    async def test_inbound_endpoint_signature_required(self, http_client):
        r = await http_client.post(
            "/api/webhooks/zenvia/inbound",
            json={"messages": []},  # sin signature
        )
        assert r.status_code == 401

    async def test_inbound_endpoint_persists_message_with_ticket_link(
        self, setup_basic, http_client, db, monkeypatch,
    ):
        # Setup: ticket abierto del cliente para que el routing lo enlace
        secret = "test-secret"
        monkeypatch.setenv("ZENVIA_WEBHOOK_SECRET", secret)
        ticket_id = new_id()
        await db.tickets.insert_one({
            "id": ticket_id, "tenant_id": setup_basic["tenant_id"],
            "client_id": setup_basic["client_id"],
            "status": "open", "is_terminal": False,
            "created_at": "2026-05-09T00:00:00Z",
        })
        body = json.dumps({
            "messages": [{
                "id": "msg-1", "from": "+5215512345678",
                "to": "biz", "timestamp": "2026-05-09T10:00:00Z",
                "contents": [{"type": "text", "text": "Hola"}],
            }],
        }).encode()
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        r = await http_client.post(
            "/api/webhooks/zenvia/inbound", content=body,
            headers={"X-Zenvia-Signature": sig, "Content-Type": "application/json"},
        )
        assert r.status_code == 200
        # Mensaje persistido con ticket_id resuelto
        m = await db.whatsapp_messages.find_one({"provider_id": "msg-1"}, {"_id": 0})
        assert m is not None
        assert m["direction"] == "inbound"
        assert m["ticket_id"] == ticket_id
        assert m["tenant_id"] == setup_basic["tenant_id"]


class TestZenviaConversation:
    async def test_get_conversation_for_ticket(self, setup_basic, http_client, db):
        ticket_id = new_id()
        for direction, txt in [("outbound", "Hola"), ("inbound", "Mi paquete?")]:
            await db.whatsapp_messages.insert_one({
                "id": new_id(), "tenant_id": setup_basic["tenant_id"],
                "ticket_id": ticket_id, "direction": direction,
                "from": "+1", "to": "+2", "text": txt,
                "media_url": None, "media_type": None,
                "provider": "zenvia", "provider_id": new_id(),
                "status": "sent", "created_at": "2026-05-09T10:00:00Z",
            })
        headers = _bearer(user_id=setup_basic["agent_id"],
                          tenant_id=setup_basic["tenant_id"], role="agent")
        r = await http_client.get(f"/api/tickets/{ticket_id}/whatsapp", headers=headers)
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 2


# ═══════════════════════════ PROMPT 22 — Heatmap ═════════════════════════
class TestHeatmap:
    async def test_buckets_groups_by_grid(self, setup_basic, db, monkeypatch):
        # Mockear geocoding para no llamar a Nominatim
        async def fake_geocode(addr, country="mx"):
            return None, None, None
        monkeypatch.setattr(geo_mod, "geocode_address", fake_geocode)

        # 3 tickets en una zona, 1 en otra
        for i, (lat, lng) in enumerate([(19.43, -99.13), (19.435, -99.131),
                                         (19.43, -99.13), (20.67, -103.34)]):
            tid = new_id()
            await db.tickets.insert_one({
                "id": tid, "tenant_id": setup_basic["tenant_id"],
                "client_id": setup_basic["client_id"],
                "carrier_code": "estafeta", "motivo_codigo": "EXTRAVIO",
                "status": "open", "created_at": "2026-05-09T10:00:00Z",
            })
            await db.evidences.insert_one({
                "id": new_id(), "tenant_id": setup_basic["tenant_id"],
                "ticket_id": tid, "kind": "pickup",
                "lat": lat, "lng": lng,
                "created_at": "2026-05-09T10:00:00Z",
            })

        result = await geo_mod.heatmap_buckets(
            tenant_id=setup_basic["tenant_id"], grid_decimals=2,
        )
        # 2 buckets: (19.43,-99.13) cluster + (20.67,-103.34)
        assert len(result) == 2
        top = result[0]
        assert top["count"] == 3
        assert top["severity"] == 1.0
        # Bucket secundario tiene severity < 1
        assert result[1]["severity"] < 1

    async def test_heatmap_endpoint(self, setup_basic, http_client, db, monkeypatch):
        async def fake_geocode(addr, country="mx"):
            return None, None, None
        monkeypatch.setattr(geo_mod, "geocode_address", fake_geocode)
        headers = _bearer(user_id=setup_basic["agent_id"],
                          tenant_id=setup_basic["tenant_id"], role="agent")
        r = await http_client.get(
            "/api/dashboard/heatmap?grid_decimals=2", headers=headers,
        )
        assert r.status_code == 200
        d = r.json()["data"]
        assert "items" in d
        assert "count" in d

    async def test_geocode_uses_cache_on_second_call(self, db, monkeypatch):
        # Mockear el HTTP call a Nominatim
        from services import geocoding as g
        monkeypatch.setattr(g, "_LAST_CALL", 0.0)
        calls = {"n": 0}
        class _FakeResp:
            status_code = 200
            def json(self):
                return [{"lat": "19.43", "lon": "-99.13", "display_name": "CDMX"}]
        class _FakeClient:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return None
            async def get(self, url, params=None, headers=None):
                calls["n"] += 1
                return _FakeResp()
        monkeypatch.setattr(g.httpx, "AsyncClient", lambda **kw: _FakeClient())

        a, b, _ = await g.geocode_address("Av. Reforma 100")
        assert a == 19.43 and b == -99.13
        assert calls["n"] == 1
        # Segunda llamada → cache (no HTTP)
        a2, b2, _ = await g.geocode_address("Av. Reforma 100")
        assert (a2, b2) == (19.43, -99.13)
        assert calls["n"] == 1, "Cache miss — debió servirse de geocode_cache"


# ═══════════════════════════ PROMPT 23 — Bulk + PDF ══════════════════════
class TestBulkActions:
    async def _seed_tickets(self, db, tenant_id, client_id, n=3):
        ids = []
        for i in range(n):
            tid = new_id()
            await db.tickets.insert_one({
                "id": tid, "tenant_id": tenant_id, "client_id": client_id,
                "status": "open", "is_terminal": False,
                "motivo_codigo": "DAÑO_PAQUETE",
                "created_at": "2026-05-09T10:00:00Z",
                "updated_at": "2026-05-09T10:00:00Z",
            })
            ids.append(tid)
        return ids

    async def test_bulk_close(self, setup_basic, http_client, db):
        ids = await self._seed_tickets(db, setup_basic["tenant_id"],
                                       setup_basic["client_id"], 3)
        headers = _bearer(user_id=setup_basic["admin_id"],
                          tenant_id=setup_basic["tenant_id"])
        r = await http_client.post(
            "/api/admin/tickets/bulk",
            json={"ticket_ids": ids, "action": "close", "payload": {}},
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json()["data"]["affected"] == 3
        # Verificar que terminales
        async for t in db.tickets.find({"id": {"$in": ids}}, {"_id": 0}):
            assert t["is_terminal"] is True
            assert t["status"] == "closed"

    async def test_bulk_close_skips_terminal(self, setup_basic, http_client, db):
        ids = await self._seed_tickets(db, setup_basic["tenant_id"],
                                       setup_basic["client_id"], 2)
        # Marcar uno como terminal (R02)
        await db.tickets.update_one({"id": ids[0]},
                                    {"$set": {"is_terminal": True, "status": "resolved"}})
        headers = _bearer(user_id=setup_basic["admin_id"],
                          tenant_id=setup_basic["tenant_id"])
        r = await http_client.post(
            "/api/admin/tickets/bulk",
            json={"ticket_ids": ids, "action": "close"},
            headers=headers,
        )
        assert r.status_code == 200
        # Sólo el segundo se cerró
        assert r.json()["data"]["affected"] == 1
        # El primero NO cambió de status (R02)
        t0 = await db.tickets.find_one({"id": ids[0]}, {"_id": 0})
        assert t0["status"] == "resolved"

    async def test_bulk_assign(self, setup_basic, http_client, db):
        ids = await self._seed_tickets(db, setup_basic["tenant_id"],
                                       setup_basic["client_id"], 2)
        headers = _bearer(user_id=setup_basic["admin_id"],
                          tenant_id=setup_basic["tenant_id"])
        r = await http_client.post(
            "/api/admin/tickets/bulk",
            json={"ticket_ids": ids, "action": "assign",
                  "payload": {"agent_id": setup_basic["target_agent_id"]}},
            headers=headers,
        )
        assert r.status_code == 200
        async for t in db.tickets.find({"id": {"$in": ids}}, {"_id": 0}):
            assert t["assigned_to"] == setup_basic["target_agent_id"]

    async def test_bulk_add_comment_creates_events(self, setup_basic, http_client, db):
        ids = await self._seed_tickets(db, setup_basic["tenant_id"],
                                       setup_basic["client_id"], 2)
        headers = _bearer(user_id=setup_basic["admin_id"],
                          tenant_id=setup_basic["tenant_id"])
        r = await http_client.post(
            "/api/admin/tickets/bulk",
            json={"ticket_ids": ids, "action": "add_comment",
                  "payload": {"text": "Revisar urgente"}},
            headers=headers,
        )
        assert r.status_code == 200
        events = [e async for e in db.ticket_events.find(
            {"ticket_id": {"$in": ids}, "event_type": "comment"}, {"_id": 0}
        )]
        assert len(events) == 2

    async def test_bulk_change_status(self, setup_basic, http_client, db):
        ids = await self._seed_tickets(db, setup_basic["tenant_id"],
                                       setup_basic["client_id"], 2)
        headers = _bearer(user_id=setup_basic["admin_id"],
                          tenant_id=setup_basic["tenant_id"])
        r = await http_client.post(
            "/api/admin/tickets/bulk",
            json={"ticket_ids": ids, "action": "change_status",
                  "payload": {"status": "waiting_carrier"}},
            headers=headers,
        )
        assert r.status_code == 200
        async for t in db.tickets.find({"id": {"$in": ids}}, {"_id": 0}):
            assert t["status"] == "waiting_carrier"
            assert t["is_terminal"] is False

    async def test_bulk_export_pdf_returns_zip(self, setup_basic, http_client, db):
        ids = await self._seed_tickets(db, setup_basic["tenant_id"],
                                       setup_basic["client_id"], 2)
        headers = _bearer(user_id=setup_basic["admin_id"],
                          tenant_id=setup_basic["tenant_id"])
        r = await http_client.post(
            "/api/admin/tickets/bulk",
            json={"ticket_ids": ids, "action": "export_pdf"},
            headers=headers,
        )
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        # Verificar el ZIP tiene 2 PDFs dentro
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        assert len(names) == 2
        for n in names:
            assert n.endswith(".pdf")
            assert n.startswith("ticket-")

    async def test_bulk_skipped_ids_other_tenant(self, setup_basic, http_client, db):
        ids = await self._seed_tickets(db, setup_basic["tenant_id"],
                                       setup_basic["client_id"], 1)
        # ID falso de otro tenant
        fake = new_id()
        headers = _bearer(user_id=setup_basic["admin_id"],
                          tenant_id=setup_basic["tenant_id"])
        r = await http_client.post(
            "/api/admin/tickets/bulk",
            json={"ticket_ids": ids + [fake], "action": "close"},
            headers=headers,
        )
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["affected"] == 1
        assert fake in d["skipped_ids"]


class TestPdfExport:
    async def test_export_single_ticket(self, setup_basic, http_client, db):
        tid = new_id()
        await db.tickets.insert_one({
            "id": tid, "tenant_id": setup_basic["tenant_id"],
            "client_id": setup_basic["client_id"], "status": "open",
            "is_terminal": False, "motivo_codigo": "EXTRAVIO",
            "tracking_id": "TRK-001",
            "created_at": "2026-05-09T10:00:00Z",
            "updated_at": "2026-05-09T10:00:00Z",
        })
        await db.ticket_events.insert_one({
            "id": new_id(), "tenant_id": setup_basic["tenant_id"],
            "ticket_id": tid, "event_type": "created",
            "description": "Ticket creado", "payload": {},
            "created_at": "2026-05-09T10:00:00Z",
        })
        headers = _bearer(user_id=setup_basic["admin_id"],
                          tenant_id=setup_basic["tenant_id"])
        r = await http_client.get(
            f"/api/admin/tickets/{tid}/export.pdf", headers=headers,
        )
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        # PDF empieza con %PDF
        assert r.content[:4] == b"%PDF"
        assert len(r.content) > 1000  # PDF no vacío

    async def test_export_404_other_tenant(self, setup_basic, http_client, db):
        tid = new_id()
        # Ticket en otro tenant
        other_tid = new_id()
        await db.tenants.insert_one({"id": other_tid, "slug": "ot",
                                     "name": "Other", "status": "active"})
        await db.tickets.insert_one({
            "id": tid, "tenant_id": other_tid, "client_id": new_id(),
            "status": "open", "created_at": "2026-05-09T10:00:00Z",
        })
        headers = _bearer(user_id=setup_basic["admin_id"],
                          tenant_id=setup_basic["tenant_id"])
        r = await http_client.get(
            f"/api/admin/tickets/{tid}/export.pdf", headers=headers,
        )
        assert r.status_code == 404
