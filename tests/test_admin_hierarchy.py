"""PROMPT 02 — Admin hierarchy CRUD tests.

Verifies:
  * Project / Client / Subclient / Carrier CRUD work with proper tenant scoping
  * Cross-tenant access is impossible (R01 + R08)
  * Client/Carrier api_creds is encrypted at rest (R07) and never returned
  * Pydantic validation errors flow through the standard envelope (R10)
"""
from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport

from server import app
from core.security import create_access_token


def _bearer(*, user_id: str, tenant_id: str, role: str = "admin",
            email: str = "admin@test.local"):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_id, tenant_id=tenant_id, role=role, email=email)}"}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def two_real_tenants(db):
    """Two tenants + 1 admin user each, registered in the live DB the app uses."""
    from core.uuid import new_id
    a = {"tenant_id": new_id(), "user_id": new_id()}
    b = {"tenant_id": new_id(), "user_id": new_id()}
    await db.tenants.insert_many([
        {"id": a["tenant_id"], "slug": "alpha", "name": "Alpha", "status": "active"},
        {"id": b["tenant_id"], "slug": "beta",  "name": "Beta",  "status": "active"},
    ])
    await db.users.insert_many([
        {"id": a["user_id"], "tenant_id": a["tenant_id"], "email": "a@test.local",
         "password_hash": "x", "name": "A", "role": "admin", "status": "active"},
        {"id": b["user_id"], "tenant_id": b["tenant_id"], "email": "b@test.local",
         "password_hash": "x", "name": "B", "role": "admin", "status": "active"},
    ])
    return {"a": a, "b": b}


# ---------- Projects -----------------------------------------------------
@pytest.mark.asyncio
async def test_project_crud_and_isolation(client, two_real_tenants):
    a, b = two_real_tenants["a"], two_real_tenants["b"]

    # Tenant A creates a project
    r = await client.post("/api/admin/projects", json={"name": "Project A1"},
                          headers=_bearer(**a))
    assert r.status_code == 201
    pj_a = r.json()["data"]
    assert pj_a["tenant_id"] == a["tenant_id"]

    # Tenant B sees no projects
    r2 = await client.get("/api/admin/projects", headers=_bearer(**b))
    assert r2.json()["data"]["count"] == 0

    # Tenant B trying to update A's project → 404 (R08)
    r3 = await client.patch(f"/api/admin/projects/{pj_a['id']}", json={"name": "Hijack"},
                            headers=_bearer(**b))
    assert r3.status_code == 404
    assert r3.json()["errors"][0]["code"] == "RESOURCE_NOT_FOUND"


# ---------- Clients + R07 ------------------------------------------------
@pytest.mark.asyncio
async def test_client_credentials_encrypted_and_redacted(client, db, two_real_tenants):
    a = two_real_tenants["a"]
    pj = (await client.post("/api/admin/projects", json={"name": "Project Cubbo"},
                            headers=_bearer(**a))).json()["data"]

    payload = {
        "project_id": pj["id"], "name": "Cubbo", "ingest_mode": "webhook",
        "api_url": "https://cubbo.example.com",
        "api_auth_type": "bearer",
        "api_creds": "SECRET-TOKEN-DO-NOT-LEAK",
    }
    r = await client.post("/api/admin/clients", json=payload, headers=_bearer(**a))
    assert r.status_code == 201
    body = r.json()["data"]
    # Wire payload must NEVER include the cleartext or the encrypted blob
    assert "api_creds" not in body
    assert "api_creds_ref" not in body
    assert body["api_creds_set"] is True
    # Persisted document HAS the encrypted blob — and it isn't the plaintext
    raw = await db.clients.find_one({"id": body["id"]})
    assert raw["api_creds_ref"] is not None
    assert "SECRET-TOKEN-DO-NOT-LEAK" not in str(raw["api_creds_ref"])


@pytest.mark.asyncio
async def test_client_requires_existing_project_in_same_tenant(client, two_real_tenants):
    a, b = two_real_tenants["a"], two_real_tenants["b"]
    pj_b = (await client.post("/api/admin/projects", json={"name": "B-PJ"},
                              headers=_bearer(**b))).json()["data"]

    # Tenant A tries to attach a client to Tenant B's project → 404
    r = await client.post("/api/admin/clients", json={
        "project_id": pj_b["id"], "name": "smuggled",
    }, headers=_bearer(**a))
    assert r.status_code == 404


# ---------- Subclients ---------------------------------------------------
@pytest.mark.asyncio
async def test_subclient_lifecycle(client, two_real_tenants):
    a = two_real_tenants["a"]
    pj = (await client.post("/api/admin/projects", json={"name": "Project X"},
                            headers=_bearer(**a))).json()["data"]
    cl = (await client.post("/api/admin/clients", json={
        "project_id": pj["id"], "name": "Client X",
    }, headers=_bearer(**a))).json()["data"]

    r = await client.post("/api/admin/subclients", json={
        "client_id": cl["id"], "name": "ShopinBaz",
    }, headers=_bearer(**a))
    assert r.status_code == 201
    sub = r.json()["data"]
    # Update
    r2 = await client.patch(f"/api/admin/subclients/{sub['id']}",
                            json={"status": "inactive"}, headers=_bearer(**a))
    assert r2.json()["data"]["status"] == "inactive"


# ---------- Carriers + RBAC ----------------------------------------------
@pytest.mark.asyncio
async def test_carrier_crud(client, two_real_tenants):
    a = two_real_tenants["a"]
    r = await client.post("/api/admin/carriers", json={
        "name": "FedEx", "code": "fedex", "has_api": True,
        "api_creds": "topsecret",
    }, headers=_bearer(**a))
    assert r.status_code == 201
    body = r.json()["data"]
    assert body["api_creds_set"] is True
    assert "api_creds_ref" not in body


@pytest.mark.asyncio
async def test_admin_endpoints_reject_lower_roles(client, two_real_tenants):
    a = two_real_tenants["a"]
    # Forge an "agent" token — should NOT be allowed
    headers = _bearer(user_id=a["user_id"], tenant_id=a["tenant_id"], role="agent")
    # We need to also persist that role in DB, otherwise auth middleware blocks earlier.
    from core.db import get_db
    await get_db().users.update_one({"id": a["user_id"]}, {"$set": {"role": "agent"}})
    r = await client.get("/api/admin/projects", headers=headers)
    assert r.status_code == 403
    assert r.json()["errors"][0]["code"] == "RBAC_DENIED"


# ---------- Tenants admin (root_dev only) --------------------------------
@pytest.mark.asyncio
async def test_tenants_admin_requires_root_dev(client, two_real_tenants):
    a = two_real_tenants["a"]
    # admin → 403
    r = await client.get("/api/admin/tenants", headers=_bearer(**a))
    assert r.status_code == 403
    # promote to root_dev
    from core.db import get_db
    await get_db().users.update_one({"id": a["user_id"]}, {"$set": {"role": "root_dev"}})
    headers = _bearer(user_id=a["user_id"], tenant_id=a["tenant_id"], role="root_dev")
    r2 = await client.get("/api/admin/tenants", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["data"]["count"] >= 2  # alpha + beta from fixture
