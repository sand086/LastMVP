"""Iter18 — Admin Users CRUD (root_dev | superadmin only).

Endpoints tested:
  - GET    /api/admin/users
  - POST   /api/admin/users
  - PATCH  /api/admin/users/{id}
  - POST   /api/admin/users/{id}/reset-password
  - DELETE /api/admin/users/{id}
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id


def _bearer(*, user_id: str, tenant_id: str, role: str = "root_dev",
            email: str = "x@t"):
    tok = create_access_token(user_id=user_id, tenant_id=tenant_id,
                              role=role, email=email)
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def env(db):
    tid = new_id()
    root_id = new_id()
    super_id = new_id()
    admin_id = new_id()
    agent_id = new_id()
    cl_id = new_id()
    await db.tenants.insert_one({"id": tid, "slug": "users-iter18",
                                 "name": "T", "status": "active"})
    await db.users.insert_many([
        {"id": root_id, "tenant_id": tid, "email": "root@t",
         "role": "root_dev", "status": "active"},
        {"id": super_id, "tenant_id": tid, "email": "super@t",
         "role": "superadmin", "status": "active"},
        {"id": admin_id, "tenant_id": tid, "email": "ad@t",
         "role": "admin", "status": "active"},
        {"id": agent_id, "tenant_id": tid, "email": "ag@t",
         "role": "agent", "status": "active"},
    ])
    await db.clients.insert_one({"id": cl_id, "tenant_id": tid, "name": "Cliente"})
    return {"tid": tid, "root": root_id, "super": super_id,
            "admin": admin_id, "agent": agent_id, "cl": cl_id}


class TestRbac:
    async def test_admin_allowed(self, env, http_client):
        # Bundle G+ — admin ahora puede listar usuarios (puede invitar internos read-only/agents)
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"], role="admin")
        r = await http_client.get("/api/admin/users", headers=h)
        assert r.status_code == 200

    async def test_agent_forbidden(self, env, http_client):
        h = _bearer(user_id=env["agent"], tenant_id=env["tid"], role="agent")
        r = await http_client.get("/api/admin/users", headers=h)
        assert r.status_code == 403

    async def test_superadmin_ok(self, env, http_client):
        h = _bearer(user_id=env["super"], tenant_id=env["tid"], role="superadmin")
        r = await http_client.get("/api/admin/users", headers=h)
        assert r.status_code == 200


class TestList:
    async def test_returns_tenant_users(self, env, http_client):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        r = await http_client.get("/api/admin/users", headers=h)
        d = r.json()["data"]
        assert d["count"] == 4
        emails = {u["email"] for u in d["items"]}
        assert {"root@t", "super@t", "ad@t", "ag@t"} == emails
        assert "agent" in d["manageable_roles"]
        assert "root_dev" not in d["manageable_roles"]

    async def test_filter_by_role(self, env, http_client):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        r = await http_client.get("/api/admin/users?role=agent", headers=h)
        assert r.json()["data"]["count"] == 1

    async def test_filter_by_search(self, env, http_client):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        r = await http_client.get("/api/admin/users?q=ad", headers=h)
        # Match "ad@t"
        assert r.json()["data"]["count"] == 1

    async def test_tenant_isolation(self, env, http_client, db):
        # Create another tenant's user
        other_tid = new_id()
        await db.users.insert_one({
            "id": new_id(), "tenant_id": other_tid, "email": "other@t",
            "role": "agent", "status": "active",
        })
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        r = await http_client.get("/api/admin/users", headers=h)
        emails = {u["email"] for u in r.json()["data"]["items"]}
        assert "other@t" not in emails


class TestCreate:
    async def test_creates_with_temp_password(self, env, http_client):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        r = await http_client.post("/api/admin/users", headers=h, json={
            "email": "NEW@t.com", "name": "New", "role": "agent",
        })
        assert r.status_code == 201
        d = r.json()["data"]
        assert d["email"] == "new@t.com"  # lowercased
        assert d["role"] == "agent"
        assert d["status"] == "active"
        assert d["must_reset_password"] is True
        assert "temp_password" in d
        assert len(d["temp_password"]) == 12

    async def test_email_uniqueness(self, env, http_client):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        r = await http_client.post("/api/admin/users", headers=h, json={
            "email": "ag@t", "name": "Dup", "role": "agent",
        })
        assert r.status_code == 422
        assert r.json()["errors"][0]["field"] == "email"

    async def test_invalid_email(self, env, http_client):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        r = await http_client.post("/api/admin/users", headers=h, json={
            "email": "bad-email", "name": "X", "role": "agent",
        })
        assert r.status_code == 422

    async def test_client_viewer_requires_client_id(self, env, http_client):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        r = await http_client.post("/api/admin/users", headers=h, json={
            "email": "viewer@t.com", "name": "V", "role": "client_viewer",
        })
        assert r.status_code == 422
        assert r.json()["errors"][0]["field"] == "client_id"

    async def test_cannot_create_root_dev(self, env, http_client):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        r = await http_client.post("/api/admin/users", headers=h, json={
            "email": "newroot@t", "name": "R", "role": "root_dev",
        })
        # role is Literal — pydantic rejects
        assert r.status_code == 422


class TestUpdate:
    async def test_patch_role(self, env, http_client):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        r = await http_client.patch(f"/api/admin/users/{env['agent']}",
                                     headers=h, json={"role": "supervisor"})
        assert r.status_code == 200
        assert r.json()["data"]["role"] == "supervisor"

    async def test_cannot_modify_root_dev(self, env, http_client):
        h = _bearer(user_id=env["super"], tenant_id=env["tid"], role="superadmin")
        r = await http_client.patch(f"/api/admin/users/{env['root']}",
                                     headers=h, json={"name": "Hacked"})
        assert r.status_code == 403

    async def test_cannot_self_degrade(self, env, http_client):
        # super tries to degrade himself to admin
        h = _bearer(user_id=env["super"], tenant_id=env["tid"], role="superadmin")
        r = await http_client.patch(f"/api/admin/users/{env['super']}",
                                     headers=h, json={"role": "admin"})
        assert r.status_code == 422
        assert "rol" in r.json()["errors"][0]["message"].lower()

    async def test_email_uniqueness_on_update(self, env, http_client):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        # try to set ag@t's email to super@t
        r = await http_client.patch(f"/api/admin/users/{env['agent']}",
                                     headers=h, json={"email": "super@t"})
        assert r.status_code == 422


class TestResetPassword:
    async def test_generates_new_temp(self, env, http_client):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        r = await http_client.post(
            f"/api/admin/users/{env['agent']}/reset-password", headers=h,
        )
        assert r.status_code == 200
        assert "temp_password" in r.json()["data"]
        assert len(r.json()["data"]["temp_password"]) == 12

    async def test_cannot_reset_root_dev(self, env, http_client):
        h = _bearer(user_id=env["super"], tenant_id=env["tid"], role="superadmin")
        r = await http_client.post(
            f"/api/admin/users/{env['root']}/reset-password", headers=h,
        )
        assert r.status_code == 403


class TestDelete:
    async def test_soft_delete(self, env, http_client, db):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        r = await http_client.delete(f"/api/admin/users/{env['agent']}", headers=h)
        assert r.status_code == 200
        doc = await db.users.find_one({"id": env["agent"]}, {"_id": 0})
        assert doc["status"] == "deleted"
        assert "deleted_by" in doc

    async def test_cannot_self_delete(self, env, http_client):
        h = _bearer(user_id=env["super"], tenant_id=env["tid"], role="superadmin")
        r = await http_client.delete(f"/api/admin/users/{env['super']}", headers=h)
        assert r.status_code == 422

    async def test_cannot_delete_root_dev(self, env, http_client):
        h = _bearer(user_id=env["super"], tenant_id=env["tid"], role="superadmin")
        r = await http_client.delete(f"/api/admin/users/{env['root']}", headers=h)
        assert r.status_code == 403

    async def test_cannot_delete_last_superadmin(self, env, http_client):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"])
        r = await http_client.delete(f"/api/admin/users/{env['super']}", headers=h)
        assert r.status_code == 422
        assert "último" in r.json()["errors"][0]["message"]
