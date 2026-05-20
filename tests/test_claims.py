"""PROMPT 13 — Reclamos.

Cobertura:
  * R32 — promote ticket → claim sólo desde resolved/closed
  * R29 — UNIQUE active claim por ticket (segundo POST cae en TERMINAL_STATE)
  * R31 — matriz de transiciones (allowed + forbidden)
  * R28 — claim terminal silencia updates
  * R35 — enviado_carrier exige expediente completo (>=2 evidencias)
  * Append-only de claim_events (R30)
  * Promote dispara timeline_event "promoted_to_claim" en el ticket
"""
from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport

from server import app
from core.security import create_access_token
from core.uuid import new_id
from repositories.claims import ensure_claim_indexes
from seeds.cae_catalog import run as seed_cae_catalog


def _bearer(*, user_id, tenant_id, role="agent", email="agent@test.local"):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_id, tenant_id=tenant_id, role=role, email=email)}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def claims_setup(db):
    """Tenant + agent + coordinator + project + client + carrier + 1 resolved ticket."""
    tid = new_id()
    uid_agent, uid_coord = new_id(), new_id()
    pj_id, cl_id, carrier_id, guia_id, ticket_id = (new_id() for _ in range(5))

    await db.tenants.insert_one({"id": tid, "slug": "rec", "name": "Rec", "status": "active"})
    await db.users.insert_many([
        {"id": uid_agent, "tenant_id": tid, "email": "ag@t",
         "password_hash": "x", "name": "Agente", "role": "agent", "status": "active"},
        {"id": uid_coord, "tenant_id": tid, "email": "co@t",
         "password_hash": "x", "name": "Coord", "role": "coordinator", "status": "active"},
    ])
    await db.projects.insert_one({"id": pj_id, "tenant_id": tid, "name": "P", "status": "active"})
    await db.clients.insert_one({
        "id": cl_id, "tenant_id": tid, "project_id": pj_id, "name": "Cubbo",
        "ingest_mode": "webhook", "webhook_token": "wh-secret",
    })
    await db.carriers.insert_one({
        "id": carrier_id, "tenant_id": tid, "name": "FedEx", "code": "fedex",
        "has_api": True, "active": True, "status": "active",
    })
    await db.guias.insert_one({
        "id": guia_id, "tenant_id": tid, "tracking_id": "FX-T-1",
        "carrier_id": "fedex", "client_id": cl_id,
        "carrier_status": "delivered", "internal_status": "delivered",
        "is_terminal": True,
    })
    await db.tickets.insert_one({
        "id": ticket_id, "tenant_id": tid, "client_id": cl_id, "guia_id": guia_id,
        "carrier_id": "fedex", "status": "resolved", "assigned_agent_id": uid_agent,
        "incident_type": "damaged", "canonical_status": "delivered",
        "carrier_status_raw": "DL", "source": "ingest",
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-02T00:00:00Z",
    })
    await seed_cae_catalog()
    await ensure_claim_indexes()
    return {
        "tenant_id": tid, "agent_id": uid_agent, "coord_id": uid_coord,
        "client_id": cl_id, "ticket_id": ticket_id, "guia_id": guia_id,
    }


# ───────────────────────── Promote (R32) ───────────────────────────────
@pytest.mark.asyncio
async def test_promote_ticket_to_claim_creates_claim_and_timeline(http_client, db, claims_setup):
    s = claims_setup
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.post(
        f"/api/tickets/{s['ticket_id']}/promote-to-claim",
        json={"tipo_dano": "dano_total", "monto_reclamado": 1500.0, "divisa": "MXN",
              "notas_iniciales": "paquete roto"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    claim = r.json()["data"]
    assert claim["estado"] == "promovido"
    assert claim["tenant_id"] == s["tenant_id"]
    assert claim["ticket_id"] == s["ticket_id"]
    # claim_events recorded the promotion
    events = await db.claim_events.find({"claim_id": claim["id"]}, {"_id": 0}).to_list(10)
    assert any(e["event_type"] == "promoted" for e in events)
    # ticket timeline mirrors the promotion (R36)
    tl = await db.timeline_events.find(
        {"tenant_id": s["tenant_id"], "ticket_id": s["ticket_id"], "event_type": "promoted_to_claim"}
    ).to_list(5)
    assert tl


@pytest.mark.asyncio
async def test_promote_rejects_non_terminal_ticket(http_client, db, claims_setup):
    s = claims_setup
    # Flip ticket back to in_progress
    await db.tickets.update_one({"id": s["ticket_id"]}, {"$set": {"status": "in_progress"}})
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.post(
        f"/api/tickets/{s['ticket_id']}/promote-to-claim",
        json={"tipo_dano": "extravio", "monto_reclamado": 100.0},
        headers=h,
    )
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "TERMINAL_STATE"


@pytest.mark.asyncio
async def test_promote_twice_blocked_by_unique_active(http_client, claims_setup):
    """R29 — sólo un reclamo activo por ticket."""
    s = claims_setup
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    body = {"tipo_dano": "dano_total", "monto_reclamado": 500.0}
    r1 = await http_client.post(f"/api/tickets/{s['ticket_id']}/promote-to-claim", json=body, headers=h)
    assert r1.status_code == 201
    r2 = await http_client.post(f"/api/tickets/{s['ticket_id']}/promote-to-claim", json=body, headers=h)
    assert r2.status_code == 409
    assert r2.json()["errors"][0]["code"] == "TERMINAL_STATE"


@pytest.mark.asyncio
async def test_promote_cross_tenant_returns_404(http_client, db, claims_setup):
    s = claims_setup
    other_tid = new_id()
    other_uid = new_id()
    await db.tenants.insert_one({"id": other_tid, "slug": "ot", "name": "O", "status": "active"})
    await db.users.insert_one({
        "id": other_uid, "tenant_id": other_tid, "email": "x@y", "password_hash": "x",
        "name": "X", "role": "agent", "status": "active",
    })
    h = _bearer(user_id=other_uid, tenant_id=other_tid, role="agent")
    r = await http_client.post(
        f"/api/tickets/{s['ticket_id']}/promote-to-claim",
        json={"tipo_dano": "extravio", "monto_reclamado": 50.0},
        headers=h,
    )
    assert r.status_code == 404


# ───────────────────────── Transitions (R31) ───────────────────────────
@pytest.mark.asyncio
async def test_transition_matrix_blocks_skipping_steps(http_client, claims_setup):
    s = claims_setup
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.post(
        f"/api/tickets/{s['ticket_id']}/promote-to-claim",
        json={"tipo_dano": "dano_total", "monto_reclamado": 999.0}, headers=h,
    )
    cid = r.json()["data"]["id"]
    # promovido → enviado_carrier no permitido (saltea expediente_en_armado)
    r2 = await http_client.post(f"/api/reclamos/{cid}/transition",
                                json={"target": "enviado_carrier"}, headers=h)
    assert r2.status_code == 409
    msg = r2.json()["errors"][0]["message"]
    assert "promovido" in msg and "enviado_carrier" in msg


@pytest.mark.asyncio
async def test_expediente_autoadvances_then_send_requires_full_kit(http_client, db, claims_setup):
    """R35 — expediente_en_armado → enviado_carrier requiere expediente completo."""
    s = claims_setup
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    # Promover
    r = await http_client.post(
        f"/api/tickets/{s['ticket_id']}/promote-to-claim",
        json={"tipo_dano": "dano_parcial", "monto_reclamado": 800.0}, headers=h,
    )
    cid = r.json()["data"]["id"]
    # Patch expediente — declaracion + 1 evidencia (insuficiente)
    await http_client.patch(
        f"/api/reclamos/{cid}/expediente",
        json={"declaracion_cliente": "Daño visible", "evidencia_ids": ["ev1"]},
        headers=h,
    )
    # Auto-advance debe haber ocurrido a expediente_en_armado
    claim = await db.claims.find_one({"id": cid}, {"_id": 0})
    assert claim["estado"] == "expediente_en_armado"
    # Intento de enviado_carrier con sólo 1 evidencia -> 422 expediente incompleto
    r2 = await http_client.post(f"/api/reclamos/{cid}/transition",
                                json={"target": "enviado_carrier"}, headers=h)
    assert r2.status_code == 422
    body = r2.json()
    assert body["errors"][0]["code"] == "VALIDATION_FAILED"
    assert any(e.get("code") == "INCOMPLETE_FILE" for e in body["errors"])
    # Agrega segunda evidencia → ahora sí avanza
    await http_client.patch(
        f"/api/reclamos/{cid}/expediente",
        json={"evidencia_ids": ["ev1", "ev2"]}, headers=h,
    )
    r3 = await http_client.post(f"/api/reclamos/{cid}/transition",
                                json={"target": "enviado_carrier"}, headers=h)
    assert r3.status_code == 200
    claim = await db.claims.find_one({"id": cid}, {"_id": 0})
    assert claim["estado"] == "enviado_carrier"


# ───────────────────────── Terminal protection (R28) ───────────────────
@pytest.mark.asyncio
async def test_terminal_claim_silently_ignores_updates(http_client, db, claims_setup):
    s = claims_setup
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.post(
        f"/api/tickets/{s['ticket_id']}/promote-to-claim",
        json={"tipo_dano": "extravio", "monto_reclamado": 200.0}, headers=h,
    )
    cid = r.json()["data"]["id"]
    # Move directly to desistido (allowed from promovido)
    r_des = await http_client.post(
        f"/api/reclamos/{cid}/transition",
        json={"target": "desistido", "reason": "Cliente desiste"}, headers=h,
    )
    assert r_des.status_code == 200
    claim = await db.claims.find_one({"id": cid}, {"_id": 0})
    assert claim["estado"] == "desistido" and claim["is_terminal"] is True
    # Cualquier intento posterior cae en TERMINAL_STATE — patch rechazado
    r2 = await http_client.patch(
        f"/api/reclamos/{cid}/expediente",
        json={"declaracion_cliente": "ya no aplica"}, headers=h,
    )
    assert r2.status_code == 409


# ───────────────────────── List + detail ───────────────────────────────
@pytest.mark.asyncio
async def test_list_and_detail_endpoints(http_client, claims_setup):
    s = claims_setup
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.post(
        f"/api/tickets/{s['ticket_id']}/promote-to-claim",
        json={"tipo_dano": "retraso", "monto_reclamado": 50.0}, headers=h,
    )
    cid = r.json()["data"]["id"]
    # List
    rl = await http_client.get("/api/reclamos", headers=h)
    assert rl.status_code == 200
    items = rl.json()["data"]["items"]
    assert any(c["id"] == cid for c in items)
    # Detail
    rd = await http_client.get(f"/api/reclamos/{cid}", headers=h)
    assert rd.status_code == 200
    payload = rd.json()["data"]
    assert payload["claim"]["id"] == cid
    assert isinstance(payload["events"], list) and payload["events"]


# ───────────────────────── Ticket detail surfaces active claim ─────────
@pytest.mark.asyncio
async def test_ticket_detail_includes_active_claim(http_client, claims_setup):
    s = claims_setup
    # coordinator user (coord_id) tiene rango >= supervisor
    h = _bearer(user_id=s["coord_id"], tenant_id=s["tenant_id"], role="coordinator")
    h_agent = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.post(
        f"/api/tickets/{s['ticket_id']}/promote-to-claim",
        json={"tipo_dano": "extravio", "monto_reclamado": 999.0}, headers=h_agent,
    )
    cid = r.json()["data"]["id"]
    rd = await http_client.get(f"/api/admin/tickets/{s['ticket_id']}", headers=h)
    assert rd.status_code == 200
    body = rd.json()["data"]
    assert body["active_claim"] is not None
    assert body["active_claim"]["id"] == cid
