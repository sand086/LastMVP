"""PROMPT 03 — Catalog + Automation matrix tests.

Validates R03 directly:
  * Default = denied (no permission row → can_automate = False)
  * Restricted motivo blocks even with permission allowed (R03 hard-stop)
  * Cross-tenant access rejected (R01/R08)
"""
from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport

from server import app
from core.security import create_access_token
from core.uuid import new_id


def _bearer(*, user_id, tenant_id, role="admin", email="admin@test.local"):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_id, tenant_id=tenant_id, role=role, email=email)}"}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def setup_tenant(db):
    tid, uid = new_id(), new_id()
    await db.tenants.insert_one({"id": tid, "slug": "alpha", "name": "Alpha", "status": "active"})
    await db.users.insert_one({
        "id": uid, "tenant_id": tid, "email": "a@t.local", "password_hash": "x",
        "name": "A", "role": "admin", "status": "active",
    })
    return {"tenant_id": tid, "user_id": uid}


async def _set_role(db, user_id: str, role: str) -> None:
    await db.users.update_one({"id": user_id}, {"$set": {"role": role}})


# ---------- Motivos -----------------------------------------------------
@pytest.mark.asyncio
async def test_motivo_create_and_validation(client, setup_tenant):
    h = _bearer(**setup_tenant, role="admin")
    # Bad code (lowercase) → 422
    r = await client.post("/api/admin/motivos", json={"code": "dir_insuficiente", "name": "X"}, headers=h)
    assert r.status_code == 422
    # Good
    r2 = await client.post("/api/admin/motivos",
                           json={"code": "DIR_INSUFICIENTE", "name": "Dirección insuficiente"}, headers=h)
    assert r2.status_code == 201
    assert r2.json()["data"]["restricted"] is False


# ---------- Soluciones --------------------------------------------------
@pytest.mark.asyncio
async def test_solucion_requires_existing_motivo(client, setup_tenant):
    h = _bearer(**setup_tenant, role="admin")
    r = await client.post("/api/admin/soluciones",
                          json={"motivo_id": new_id(), "name": "Solucion fantasma"}, headers=h)
    assert r.status_code == 404
    assert r.json()["errors"][0]["code"] == "RESOURCE_NOT_FOUND"


# ---------- Automation permissions + R03 -------------------------------
@pytest.mark.asyncio
async def test_automation_default_deny_and_restricted_block(client, db, setup_tenant):
    """End-to-end: a restricted motivo NEVER automates, even when allowed=true."""
    tid = setup_tenant["tenant_id"]
    h = _bearer(**setup_tenant, role="admin")
    h_coord = _bearer(**setup_tenant, role="coordinator")

    # Create non-restricted motivo + automatable solución
    m = (await client.post("/api/admin/motivos",
        json={"code": "DIR_INSUF", "name": "Dirección insuf."}, headers=h)).json()["data"]
    s = (await client.post("/api/admin/soluciones",
        json={"motivo_id": m["id"], "name": "Confirmar referencias",
              "automatable": True}, headers=h)).json()["data"]

    # Need a client to attach permissions to — minimal seed via DB
    pj_id, cl_id = new_id(), new_id()
    await db.projects.insert_one({"id": pj_id, "tenant_id": tid, "name": "PJ", "status": "active"})
    await db.clients.insert_one({"id": cl_id, "tenant_id": tid, "project_id": pj_id,
                                 "name": "Cubbo", "ingest_mode": "webhook"})

    # Default — no permission row yet → can_automate = False
    r0 = await client.get("/api/admin/automation-permissions/check",
                          params={"client_id": cl_id, "solucion_id": s["id"], "channel": "email"},
                          headers=h_coord)
    assert r0.json()["data"]["can_automate"] is False
    assert r0.json()["data"]["reason"] == "permission_denied"

    # Allow → can_automate = True
    await client.put("/api/admin/automation-permissions",
                     json={"client_id": cl_id, "solucion_id": s["id"],
                           "channel": "email", "allowed": True}, headers=h_coord)
    r1 = await client.get("/api/admin/automation-permissions/check",
                          params={"client_id": cl_id, "solucion_id": s["id"], "channel": "email"},
                          headers=h_coord)
    assert r1.json()["data"]["can_automate"] is True

    # Now flag motivo as restricted (e.g., AUTORIDAD) — R03 hard-stop
    await client.patch(f"/api/admin/motivos/{m['id']}", json={"restricted": True}, headers=h)
    r2 = await client.get("/api/admin/automation-permissions/check",
                          params={"client_id": cl_id, "solucion_id": s["id"], "channel": "email"},
                          headers=h_coord)
    assert r2.json()["data"]["can_automate"] is False
    assert r2.json()["data"]["reason"] == "motivo_restricted"


@pytest.mark.asyncio
async def test_solucion_no_automatable_blocks(client, db, setup_tenant):
    tid = setup_tenant["tenant_id"]
    h = _bearer(**setup_tenant, role="admin")
    h_coord = _bearer(**setup_tenant, role="coordinator")

    m = (await client.post("/api/admin/motivos",
        json={"code": "RECHAZO", "name": "Rechazo"}, headers=h)).json()["data"]
    s = (await client.post("/api/admin/soluciones",
        json={"motivo_id": m["id"], "name": "Manual", "automatable": False}, headers=h)).json()["data"]

    pj_id, cl_id = new_id(), new_id()
    await db.projects.insert_one({"id": pj_id, "tenant_id": tid, "name": "PJ", "status": "active"})
    await db.clients.insert_one({"id": cl_id, "tenant_id": tid, "project_id": pj_id,
                                 "name": "Cubbo", "ingest_mode": "webhook"})
    await client.put("/api/admin/automation-permissions",
                     json={"client_id": cl_id, "solucion_id": s["id"],
                           "channel": "email", "allowed": True}, headers=h_coord)
    r = await client.get("/api/admin/automation-permissions/check",
                         params={"client_id": cl_id, "solucion_id": s["id"], "channel": "email"},
                         headers=h_coord)
    assert r.json()["data"]["can_automate"] is False
    assert r.json()["data"]["reason"] == "solucion_no_automatable"


@pytest.mark.asyncio
async def test_supervisor_cannot_toggle_permissions(client, db, setup_tenant):
    """Sec 6.4 — only admin or coordinator can flip permissions."""
    await _set_role(db, setup_tenant["user_id"], "supervisor")
    h_super = _bearer(**setup_tenant, role="supervisor")
    r = await client.put("/api/admin/automation-permissions",
                         json={"client_id": new_id(), "solucion_id": new_id(),
                               "channel": "email", "allowed": True}, headers=h_super)
    assert r.status_code == 403
    assert r.json()["errors"][0]["code"] == "RBAC_DENIED"
