"""PROMPT 05/06/07 — WorkflowEngine + CAE + Adapters.

Cobertura:
  * Adapter mock determinístico devuelve un raw_code conocido por carrier
  * Normalizer hits the catalog → canonical correcto
  * Normalizer miss registra en cae_unmapped_codes (R25)
  * Ingest webhook con raw_code → normalize → WorkflowEngine crea ticket de incidente
  * Ticket auto-asignado al primer agente activo
  * timeline_events emite 'created' + 'assigned' (R04 append-only)
  * Sandbox endpoint devuelve hit/miss + sugerencia
  * promote-unmapped mueve fila de unmapped al catálogo
"""
from __future__ import annotations
import json
import pytest
from httpx import AsyncClient, ASGITransport

from server import app
from core.hmac import sign
from core.security import create_access_token
from core.uuid import new_id
from seeds.cae_catalog import run as seed_cae_catalog


def _bearer(*, user_id, tenant_id, role="admin", email="admin@test.local"):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_id, tenant_id=tenant_id, role=role, email=email)}"}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def setup(db):
    """Tenant + admin + agent + project + carrier (fedex) + webhook client."""
    tid, uid_admin, uid_agent = new_id(), new_id(), new_id()
    pj_id, cl_id, carrier_id = new_id(), new_id(), new_id()
    token = "wh-secret-1234567890abcdef"
    await db.tenants.insert_one({"id": tid, "slug": "alpha", "name": "Alpha", "status": "active"})
    await db.users.insert_many([
        {"id": uid_admin, "tenant_id": tid, "email": "a@t", "password_hash": "x",
         "name": "Admin", "role": "root_dev", "status": "active"},
        {"id": uid_agent, "tenant_id": tid, "email": "g@t", "password_hash": "x",
         "name": "Agente", "role": "agent", "status": "active"},
    ])
    await db.projects.insert_one({"id": pj_id, "tenant_id": tid, "name": "P", "status": "active"})
    await db.clients.insert_one({
        "id": cl_id, "tenant_id": tid, "project_id": pj_id, "name": "Cubbo",
        "ingest_mode": "webhook", "webhook_token": token,
    })
    await db.carriers.insert_one({
        "id": carrier_id, "tenant_id": tid, "name": "FedEx",
        "code": "fedex", "has_api": True, "active": True, "status": "active",
    })
    # Re-seed the global catalog (drop_database wiped it)
    await seed_cae_catalog()
    return {
        "tenant_id": tid, "admin_id": uid_admin, "agent_id": uid_agent,
        "client_id": cl_id, "carrier_id": carrier_id, "token": token,
    }


# ───── Adapters (PROMPT 07) ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_adapter_mock_returns_known_raw_code():
    from services.cae.adapters.anchor_stubs import get_adapter
    adapter = get_adapter("fedex")
    event = await adapter.get_raw_status("FX-001")
    assert event.carrier_id == "fedex"
    assert event.raw_code in adapter.NATIVE_CODES


# ───── Normalizer (PROMPT 06) ───────────────────────────────────────────
@pytest.mark.asyncio
async def test_normalizer_hits_catalog(setup):
    from services.cae.normalizer import StatusNormalizer
    from services.cae.interface import RawCarrierEvent
    from datetime import datetime, timezone
    norm = StatusNormalizer(tenant_id=setup["tenant_id"])
    event = RawCarrierEvent(
        carrier_id="fedex", tracking_id="X-1", raw_code="DL",
        raw_description=None, raw_payload={}, api_version="v1",
        event_at=datetime.now(timezone.utc),
    )
    res = await norm.normalize(event)
    assert res.canonical_status == "delivered"
    assert res.is_terminal is True
    assert res.confidence >= 90


@pytest.mark.asyncio
async def test_normalizer_miss_registers_unmapped(db, setup):
    from services.cae.normalizer import StatusNormalizer
    from services.cae.interface import RawCarrierEvent
    from datetime import datetime, timezone
    norm = StatusNormalizer(tenant_id=setup["tenant_id"])
    event = RawCarrierEvent(
        carrier_id="fedex", tracking_id="X-9", raw_code="ZZZ_NEW",
        raw_description="raro", raw_payload={}, api_version="v1",
        event_at=datetime.now(timezone.utc),
    )
    res = await norm.normalize(event)
    assert res.canonical_status == "unknown"
    assert res.confidence == 0
    row = await db.cae_unmapped_codes.find_one({"carrier_id": "fedex", "raw_code": "ZZZ_NEW"})
    assert row is not None and row["occurrences"] >= 1


# ───── End-to-end: Ingest → Normalizer → WorkflowEngine ────────────────
def _payload(**over):
    base = {"tracking_id": "FX-LATAM-1", "carrier_code": "fedex",
            "carrier_status": "Excepción de dirección", "raw_code": "DE"}
    base.update(over)
    return json.dumps(base, separators=(",", ":")).encode("utf-8")


@pytest.mark.asyncio
async def test_ingest_with_incident_creates_assigned_ticket(client, db, setup):
    body = _payload()
    r = await client.post(
        f"/api/guias/ingest/webhook?client_id={setup['client_id']}",
        content=body,
        headers={"X-MyE-Signature": sign(setup["token"], body),
                 "Content-Type": "application/json"},
    )
    assert r.status_code == 202
    data = r.json()["data"]
    assert data["action"] == "created"

    tickets = await db.tickets.find({"tenant_id": setup["tenant_id"]}, {"_id": 0}).to_list(length=10)
    assert len(tickets) == 1
    t = tickets[0]
    assert t["status"] == "in_progress"
    assert t["assigned_agent_id"] == setup["agent_id"]
    assert t["incident_type"] == "address_issue"

    timeline = await db.timeline_events.find(
        {"tenant_id": setup["tenant_id"], "ticket_id": t["id"]}, {"_id": 0},
    ).sort("created_at", 1).to_list(length=10)
    types = [e["event_type"] for e in timeline]
    assert "created" in types and "assigned" in types


@pytest.mark.asyncio
async def test_ingest_then_delivered_resolves_open_ticket(client, db, setup):
    body1 = _payload(carrier_status="Excepción", raw_code="DE")
    await client.post(f"/api/guias/ingest/webhook?client_id={setup['client_id']}",
                      content=body1, headers={"X-MyE-Signature": sign(setup["token"], body1)})
    body2 = _payload(carrier_status="Entregado", raw_code="DL")
    r = await client.post(f"/api/guias/ingest/webhook?client_id={setup['client_id']}",
                          content=body2, headers={"X-MyE-Signature": sign(setup["token"], body2)})
    assert r.json()["data"]["is_terminal"] is True
    tickets = await db.tickets.find({"tenant_id": setup["tenant_id"]}, {"_id": 0}).to_list(length=10)
    assert len(tickets) == 1
    assert tickets[0]["status"] == "resolved"


# ───── CAE Sandbox + promote-unmapped ──────────────────────────────────
@pytest.mark.asyncio
async def test_sandbox_hit_and_miss(client, setup):
    h = _bearer(user_id=setup["admin_id"], tenant_id=setup["tenant_id"], role="root_dev")
    # Hit
    r = await client.post("/api/admin/cae/sandbox",
        json={"carrier_id": "fedex", "raw_code": "DL"}, headers=h)
    assert r.json()["data"]["matched"] is True
    assert r.json()["data"]["canonical_status"] == "delivered"
    # Miss with adapter default suggestion
    r2 = await client.post("/api/admin/cae/sandbox",
        json={"carrier_id": "estafeta", "raw_code": "WHO_KNOWS"}, headers=h)
    assert r2.json()["data"]["matched"] is False


@pytest.mark.asyncio
async def test_promote_unmapped_creates_catalog_row_and_drops_unmapped(client, db, setup):
    # Force an unmapped registration first
    from services.cae.normalizer import StatusNormalizer
    from services.cae.interface import RawCarrierEvent
    from datetime import datetime, timezone
    await StatusNormalizer(tenant_id=setup["tenant_id"]).normalize(
        RawCarrierEvent(carrier_id="fedex", tracking_id="X", raw_code="NEW_RAW_42",
                        raw_description="???", raw_payload={}, api_version="v1",
                        event_at=datetime.now(timezone.utc)),
    )
    h = _bearer(user_id=setup["admin_id"], tenant_id=setup["tenant_id"], role="root_dev")
    r = await client.post("/api/admin/cae/promote-unmapped", json={
        "carrier_id": "fedex", "raw_code": "NEW_RAW_42",
        "canonical_status": "exception", "incident_type": "exception",
        "is_terminal": False, "requires_action": True,
        "display_label_es": "Excepción nueva",
    }, headers=h)
    assert r.status_code == 201
    assert await db.cae_unmapped_codes.count_documents({"raw_code": "NEW_RAW_42"}) == 0
    assert await db.carrier_status_catalog.count_documents(
        {"raw_code": "NEW_RAW_42", "carrier_id": "fedex"}
    ) == 1


@pytest.mark.asyncio
async def test_admin_tickets_list_and_detail(client, db, setup):
    body = _payload()
    await client.post(f"/api/guias/ingest/webhook?client_id={setup['client_id']}",
                      content=body, headers={"X-MyE-Signature": sign(setup["token"], body)})
    h = _bearer(user_id=setup["admin_id"], tenant_id=setup["tenant_id"], role="supervisor")
    r = await client.get("/api/admin/tickets", headers=h)
    items = r.json()["data"]["items"]
    assert items
    detail = await client.get(f"/api/admin/tickets/{items[0]['id']}", headers=h)
    assert detail.status_code == 200
    body = detail.json()["data"]
    assert body["ticket"]["id"] == items[0]["id"]
    assert body["timeline"]
    assert body["guia"]
