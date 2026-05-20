"""Iter41 · Bundle G+ — ASSIGNMENT_RULES (delegación de invitación).

Formaliza qué rol puede invitar a qué otros roles. Caso de uso clave:
**Coordinator puede invitar `client_viewer` / `client_auditor` a clients del tenant**,
sin necesidad de pedirle al superadmin.

Cubre:
  - rbac.can_assign_role() y assignable_roles_for() unit tests.
  - POST /api/admin/users con guardrails por actor.role.
  - GET /api/admin/users devuelve `assignable_roles` filtrado por el actor.
  - PATCH / DELETE / RESET-PASSWORD también respetan las reglas.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token, hash_password
from core.uuid import new_id
from middleware.rbac import (
    can_assign_role, assignable_roles_for, ASSIGNMENT_RULES,
)


def _bearer(*, user_id: str, tenant_id: str, role: str,
            email: str = "x@t.io", client_id: str | None = None):
    tok = create_access_token(user_id=user_id, tenant_id=tenant_id,
                              role=role, email=email, client_id=client_id)
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def env(db):
    tid = new_id()
    cl_id = new_id()
    root_id = new_id()
    super_id = new_id()
    admin_id = new_id()
    coord_id = new_id()
    super2_id = new_id()  # supervisor
    agent_id = new_id()
    now = datetime.now(timezone.utc).isoformat()
    pwd = hash_password("x")

    await db.tenants.insert_one({
        "id": tid, "slug": "g-plus", "name": "T", "status": "active",
    })
    await db.clients.insert_one({
        "id": cl_id, "tenant_id": tid, "name": "C", "status": "active",
        "ingest_mode": "webhook",
    })
    await db.users.insert_many([
        {"id": root_id, "tenant_id": tid, "email": "root@gplus.io",
         "role": "root_dev", "status": "active", "password_hash": pwd,
         "created_at": now},
        {"id": super_id, "tenant_id": tid, "email": "super@gplus.io",
         "role": "superadmin", "status": "active", "password_hash": pwd,
         "created_at": now},
        {"id": admin_id, "tenant_id": tid, "email": "admin@gplus.io",
         "role": "admin", "status": "active", "password_hash": pwd,
         "created_at": now},
        {"id": coord_id, "tenant_id": tid, "email": "coord@gplus.io",
         "role": "coordinator", "status": "active", "password_hash": pwd,
         "created_at": now},
        {"id": super2_id, "tenant_id": tid, "email": "supervisor@gplus.io",
         "role": "supervisor", "status": "active", "password_hash": pwd,
         "created_at": now},
        {"id": agent_id, "tenant_id": tid, "email": "agent@gplus.io",
         "role": "agent", "status": "active", "password_hash": pwd,
         "created_at": now},
    ])
    return {"tid": tid, "cl": cl_id, "root": root_id, "super": super_id,
            "admin": admin_id, "coord": coord_id, "super2": super2_id,
            "agent": agent_id}


# ────────────────────────────────────────────────────────────────────────
#  Unit tests · helpers rbac
# ────────────────────────────────────────────────────────────────────────
class TestRbacHelpers:
    def test_root_can_assign_everything(self):
        for target in ASSIGNMENT_RULES["root_dev"]:
            assert can_assign_role("root_dev", target) is True

    def test_coordinator_can_only_invite_externals(self):
        assert can_assign_role("coordinator", "client_viewer") is True
        assert can_assign_role("coordinator", "client_auditor") is True
        # NO puede invitar internos
        assert can_assign_role("coordinator", "supervisor") is False
        assert can_assign_role("coordinator", "agent") is False
        assert can_assign_role("coordinator", "admin") is False
        assert can_assign_role("coordinator", "coordinator") is False
        assert can_assign_role("coordinator", "root_dev") is False

    def test_admin_can_invite_below_but_not_admin(self):
        assert can_assign_role("admin", "coordinator") is True
        assert can_assign_role("admin", "supervisor") is True
        assert can_assign_role("admin", "agent") is True
        assert can_assign_role("admin", "client_viewer") is True
        assert can_assign_role("admin", "client_auditor") is True
        # NO puede asignar admin/superadmin/root_dev (no escalación lateral)
        assert can_assign_role("admin", "admin") is False
        assert can_assign_role("admin", "superadmin") is False

    def test_supervisor_agent_external_cannot_assign(self):
        for actor in ("supervisor", "agent", "client_viewer", "client_auditor"):
            assert assignable_roles_for(actor) == []

    def test_assignable_roles_sorted_by_rank(self):
        roles = assignable_roles_for("admin")
        # Externos rank=1 primero, agent rank=2, supervisor rank=3, coordinator rank=4
        assert roles[0] in ("client_viewer", "client_auditor")
        assert roles[-1] == "coordinator"


# ────────────────────────────────────────────────────────────────────────
#  Endpoint: GET /api/admin/users — devuelve assignable_roles
# ────────────────────────────────────────────────────────────────────────
class TestListReturnsAssignableRoles:
    async def test_coordinator_sees_only_externals(self, env, http_client):
        h = _bearer(user_id=env["coord"], tenant_id=env["tid"],
                    role="coordinator", email="coord@gplus.io")
        r = await http_client.get("/api/admin/users", headers=h)
        assert r.status_code == 200
        d = r.json()["data"]
        assert set(d["assignable_roles"]) == {"client_viewer", "client_auditor"}

    async def test_admin_sees_internals_and_externals(self, env, http_client):
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"],
                    role="admin", email="admin@gplus.io")
        r = await http_client.get("/api/admin/users", headers=h)
        d = r.json()["data"]
        assert set(d["assignable_roles"]) == {
            "client_viewer", "client_auditor", "agent",
            "supervisor", "coordinator",
        }

    async def test_supervisor_forbidden(self, env, http_client):
        h = _bearer(user_id=env["super2"], tenant_id=env["tid"],
                    role="supervisor", email="supervisor@gplus.io")
        r = await http_client.get("/api/admin/users", headers=h)
        assert r.status_code == 403  # require_min_role(coordinator)


# ────────────────────────────────────────────────────────────────────────
#  Endpoint: POST /api/admin/users — guardrails de can_assign_role
# ────────────────────────────────────────────────────────────────────────
class TestCreateGuardrails:
    async def test_coordinator_invites_client_viewer_ok(self, env, http_client):
        h = _bearer(user_id=env["coord"], tenant_id=env["tid"],
                    role="coordinator", email="coord@gplus.io")
        r = await http_client.post(
            "/api/admin/users",
            json={
                "email": "new-viewer@gplus.io", "name": "New Viewer",
                "role": "client_viewer", "client_id": env["cl"],
            },
            headers=h,
        )
        assert r.status_code == 201, r.text
        assert r.json()["data"]["role"] == "client_viewer"

    async def test_coordinator_cannot_invite_supervisor(self, env, http_client):
        h = _bearer(user_id=env["coord"], tenant_id=env["tid"],
                    role="coordinator", email="coord@gplus.io")
        r = await http_client.post(
            "/api/admin/users",
            json={"email": "bad@gplus.io", "name": "X", "role": "supervisor"},
            headers=h,
        )
        assert r.status_code == 403

    async def test_coordinator_cannot_invite_admin(self, env, http_client):
        h = _bearer(user_id=env["coord"], tenant_id=env["tid"],
                    role="coordinator", email="coord@gplus.io")
        r = await http_client.post(
            "/api/admin/users",
            json={"email": "bad@gplus.io", "name": "X", "role": "admin"},
            headers=h,
        )
        assert r.status_code == 403

    async def test_admin_invites_coordinator_ok(self, env, http_client):
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"],
                    role="admin", email="admin@gplus.io")
        r = await http_client.post(
            "/api/admin/users",
            json={"email": "new-coord@gplus.io", "name": "New Coord",
                  "role": "coordinator"},
            headers=h,
        )
        assert r.status_code == 201

    async def test_admin_cannot_invite_admin(self, env, http_client):
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"],
                    role="admin", email="admin@gplus.io")
        r = await http_client.post(
            "/api/admin/users",
            json={"email": "new-admin@gplus.io", "name": "X", "role": "admin"},
            headers=h,
        )
        assert r.status_code == 403


# ────────────────────────────────────────────────────────────────────────
#  Endpoint: PATCH / RESET-PASSWORD / DELETE — guardrails
# ────────────────────────────────────────────────────────────────────────
class TestModifyGuardrails:
    async def test_coordinator_cannot_patch_admin(self, env, http_client):
        h = _bearer(user_id=env["coord"], tenant_id=env["tid"],
                    role="coordinator", email="coord@gplus.io")
        r = await http_client.patch(
            f"/api/admin/users/{env['admin']}",
            json={"name": "Hacked"},
            headers=h,
        )
        assert r.status_code == 403

    async def test_coordinator_cannot_promote_viewer_to_supervisor(
            self, env, http_client, db):
        # Crear primero un viewer al que el coord pueda tocar
        viewer_id = new_id()
        await db.users.insert_one({
            "id": viewer_id, "tenant_id": env["tid"],
            "email": "view2@gplus.io", "role": "client_viewer",
            "status": "active", "password_hash": hash_password("x"),
            "client_id": env["cl"],
        })
        h = _bearer(user_id=env["coord"], tenant_id=env["tid"],
                    role="coordinator", email="coord@gplus.io")
        r = await http_client.patch(
            f"/api/admin/users/{viewer_id}",
            json={"role": "supervisor"},  # ◄── escalación denegada
            headers=h,
        )
        assert r.status_code == 403

    async def test_coordinator_can_reset_external_password(
            self, env, http_client, db):
        viewer_id = new_id()
        await db.users.insert_one({
            "id": viewer_id, "tenant_id": env["tid"],
            "email": "view3@gplus.io", "role": "client_viewer",
            "status": "active", "password_hash": hash_password("x"),
            "client_id": env["cl"],
        })
        h = _bearer(user_id=env["coord"], tenant_id=env["tid"],
                    role="coordinator", email="coord@gplus.io")
        r = await http_client.post(
            f"/api/admin/users/{viewer_id}/reset-password", headers=h,
        )
        assert r.status_code == 200, r.text
        assert "temp_password" in r.json()["data"]

    async def test_coordinator_cannot_reset_admin_password(self, env, http_client):
        h = _bearer(user_id=env["coord"], tenant_id=env["tid"],
                    role="coordinator", email="coord@gplus.io")
        r = await http_client.post(
            f"/api/admin/users/{env['admin']}/reset-password", headers=h,
        )
        assert r.status_code == 403

    async def test_coordinator_can_delete_external(
            self, env, http_client, db):
        viewer_id = new_id()
        await db.users.insert_one({
            "id": viewer_id, "tenant_id": env["tid"],
            "email": "view4@gplus.io", "role": "client_viewer",
            "status": "active", "password_hash": hash_password("x"),
            "client_id": env["cl"],
        })
        h = _bearer(user_id=env["coord"], tenant_id=env["tid"],
                    role="coordinator", email="coord@gplus.io")
        r = await http_client.delete(
            f"/api/admin/users/{viewer_id}", headers=h,
        )
        assert r.status_code == 200

    async def test_coordinator_cannot_delete_admin(self, env, http_client):
        h = _bearer(user_id=env["coord"], tenant_id=env["tid"],
                    role="coordinator", email="coord@gplus.io")
        r = await http_client.delete(
            f"/api/admin/users/{env['admin']}", headers=h,
        )
        assert r.status_code == 403
