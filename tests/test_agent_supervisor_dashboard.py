"""PROMPT 08-10 — agent panel + supervisor + dashboard tests."""
from __future__ import annotations
import json
import pytest
from httpx import AsyncClient, ASGITransport

from server import app
from core.hmac import sign
from core.security import create_access_token
from core.uuid import new_id
from seeds.cae_catalog import run as seed_cae_catalog


def _bearer(*, user_id, tenant_id, role, email="x@y"):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_id, tenant_id=tenant_id, role=role, email=email)}"}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def setup(db):
    tid = new_id()
    admin_id, agent1_id, agent2_id, sup_id = new_id(), new_id(), new_id(), new_id()
    pj_id, cl_id = new_id(), new_id()
    token = "hookhookhookhookhookhookhookhook"
    await db.tenants.insert_one({"id": tid, "slug": "alpha", "name": "Alpha", "status": "active"})
    await db.users.insert_many([
        {"id": admin_id, "tenant_id": tid, "email": "ad@t", "password_hash": "x",
         "name": "Ad", "role": "root_dev", "status": "active"},
        {"id": agent1_id, "tenant_id": tid, "email": "a1@t", "password_hash": "x",
         "name": "Agent 1", "role": "agent", "status": "active"},
        {"id": agent2_id, "tenant_id": tid, "email": "a2@t", "password_hash": "x",
         "name": "Agent 2", "role": "agent", "status": "active"},
        {"id": sup_id, "tenant_id": tid, "email": "s@t", "password_hash": "x",
         "name": "Sup", "role": "supervisor", "status": "active"},
    ])
    await db.projects.insert_one({"id": pj_id, "tenant_id": tid, "name": "P", "status": "active"})
    await db.clients.insert_one({"id": cl_id, "tenant_id": tid, "project_id": pj_id,
                                 "name": "Cubbo", "ingest_mode": "webhook", "webhook_token": token})
    await seed_cae_catalog()
    return {"tenant_id": tid, "admin_id": admin_id,
            "agent1_id": agent1_id, "agent2_id": agent2_id,
            "sup_id": sup_id, "client_id": cl_id, "token": token}


async def _create_incident_ticket(client, setup, tracking_id="FX-AG-1"):
    body = json.dumps({
        "tracking_id": tracking_id, "carrier_code": "fedex",
        "carrier_status": "Excepción dirección", "raw_code": "DE",
    }, separators=(",", ":")).encode("utf-8")
    r = await client.post(
        f"/api/guias/ingest/webhook?client_id={setup['client_id']}",
        content=body, headers={"X-MyE-Signature": sign(setup["token"], body),
                               "Content-Type": "application/json"},
    )
    assert r.status_code == 202


# --- PROMPT 08 (agent) ---------------------------------------------------
@pytest.mark.asyncio
async def test_agent_queue_and_take(client, db, setup):
    await _create_incident_ticket(client, setup)
    h1 = _bearer(user_id=setup["agent1_id"], tenant_id=setup["tenant_id"], role="agent")
    q = await client.get("/api/agent/queue", headers=h1)
    assert q.status_code == 200
    items = q.json()["data"]
    # The first ticket was auto-assigned to agent1 (first available agent)
    assert items["totals"]["mine"] == 1

    # Create a second incident — also goes to agent1 (still first-by-created_at)
    await _create_incident_ticket(client, setup, tracking_id="FX-AG-2")
    # Reassign one to nobody so agent2 can claim it
    t = await db.tickets.find_one({"tenant_id": setup["tenant_id"], "guia_id": {"$ne": None}})
    await db.tickets.update_one({"id": t["id"]}, {"$set": {"assigned_agent_id": None,
                                                            "status": "pending"}})
    h2 = _bearer(user_id=setup["agent2_id"], tenant_id=setup["tenant_id"], role="agent")
    q2 = await client.get("/api/agent/queue", headers=h2)
    pool = q2.json()["data"]["pool"]
    assert pool, "se esperaba al menos 1 ticket sin asignar"
    take = await client.post(f"/api/agent/tickets/{pool[0]['id']}/take", headers=h2)
    assert take.status_code == 200
    assert take.json()["data"]["assigned_agent_id"] == setup["agent2_id"]


@pytest.mark.asyncio
async def test_agent_change_status(client, db, setup):
    await _create_incident_ticket(client, setup)
    t = await db.tickets.find_one({"tenant_id": setup["tenant_id"]})
    h = _bearer(user_id=setup["agent1_id"], tenant_id=setup["tenant_id"], role="agent")
    r = await client.patch(f"/api/agent/tickets/{t['id']}/status",
                           json={"status": "waiting_client", "reason": "esperando datos"},
                           headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "waiting_client"


# --- PROMPT 09 (supervisor) ---------------------------------------------
@pytest.mark.asyncio
async def test_supervisor_tickets_by_agent(client, setup):
    await _create_incident_ticket(client, setup)
    h = _bearer(user_id=setup["sup_id"], tenant_id=setup["tenant_id"], role="supervisor")
    r = await client.get("/api/supervisor/tickets-by-agent", headers=h)
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    # Agent1 picked up the incident; agent2 has 0
    by_id = {it["agent_id"]: it for it in items}
    assert by_id[setup["agent1_id"]]["open"] >= 1
    assert by_id[setup["agent2_id"]]["open"] == 0


# --- PROMPT 10 (dashboard) ----------------------------------------------
@pytest.mark.asyncio
async def test_dashboard_kpis(client, setup):
    await _create_incident_ticket(client, setup)
    h = _bearer(user_id=setup["sup_id"], tenant_id=setup["tenant_id"], role="supervisor")
    r = await client.get("/api/dashboard/kpis", headers=h)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["open_tickets"] >= 1
    assert "automation_rate_30d" in data
    # Throughput
    r2 = await client.get("/api/dashboard/throughput-7d", headers=h)
    assert r2.status_code == 200
    assert len(r2.json()["data"]["items"]) == 7
    # Incidents by type
    r3 = await client.get("/api/dashboard/incidents-by-type", headers=h)
    assert r3.status_code == 200
    types = [i["incident_type"] for i in r3.json()["data"]["items"]]
    assert "address_issue" in types


@pytest.mark.asyncio
async def test_dashboard_requires_supervisor(client, setup):
    h = _bearer(user_id=setup["agent1_id"], tenant_id=setup["tenant_id"], role="agent")
    r = await client.get("/api/dashboard/kpis", headers=h)
    assert r.status_code == 403
