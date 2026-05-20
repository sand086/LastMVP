"""Iter42 · Bundle H — UserScopeAssignment (multi-cliente para externos).

Habilita que un usuario externo (client_viewer / client_auditor) tenga acceso
a MÚLTIPLES clients del mismo tenant. Reemplaza el campo legacy
`users.client_id` (1:1) por la colección `user_scope_assignments` (1:N).

Cubre:
  - Lazy migration del campo legacy en el primer load.
  - GET /api/admin/users/{id}/scopes
  - POST /api/admin/users/{id}/scopes  (añadir client_id)
  - DELETE /api/admin/users/{id}/scopes/{assignment_id}  (quitar)
  - Multi-scope efectivo: auditor con [cl_a, cl_b] ve invocaciones de ambos.
  - Guardrails: no se permite borrar el último scope; cross-tenant denied; etc.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token, hash_password
from core.uuid import new_id


def _bearer(*, user_id: str, tenant_id: str, role: str,
            email: str = "x@h.io", client_id: str | None = None):
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
    """3 clients en 1 tenant + 1 viewer + 1 admin + invocations cross-client."""
    tid = new_id()
    cl_a = new_id()
    cl_b = new_id()
    cl_c = new_id()
    admin_id = new_id()
    coord_id = new_id()
    viewer_id = new_id()
    auditor_id = new_id()
    now = datetime.now(timezone.utc).isoformat()

    await db.tenants.insert_one({
        "id": tid, "slug": "bundle-h", "name": "T-H", "status": "active",
    })
    for cl_id, name in [(cl_a, "Cliente A"), (cl_b, "Cliente B"), (cl_c, "Cliente C")]:
        await db.clients.insert_one({
            "id": cl_id, "tenant_id": tid, "name": name, "status": "active",
            "ingest_mode": "webhook",
        })
    pwd = hash_password("Test123!")
    await db.users.insert_many([
        {"id": admin_id, "tenant_id": tid, "email": "admin@h.io",
         "role": "admin", "status": "active", "password_hash": pwd},
        {"id": coord_id, "tenant_id": tid, "email": "coord@h.io",
         "role": "coordinator", "status": "active", "password_hash": pwd},
        {"id": viewer_id, "tenant_id": tid, "email": "viewer@h.io",
         "role": "client_viewer", "status": "active", "password_hash": pwd,
         # Legacy field — debe migrarse en el primer middleware load
         "client_id": cl_a},
        {"id": auditor_id, "tenant_id": tid, "email": "auditor@h.io",
         "role": "client_auditor", "status": "active", "password_hash": pwd,
         "client_id": cl_b},
    ])
    # Invocations: 1 en cl_a, 2 en cl_b, 1 en cl_c
    for cl_id, count in [(cl_a, 1), (cl_b, 2), (cl_c, 1)]:
        for _ in range(count):
            await db.ai_invocation_log.insert_one({
                "id": new_id(), "tenant_id": tid, "client_id": cl_id,
                "feature_code": "classify_motivo", "status": "ok",
                "cost_usd": 0.10, "created_at": now,
            })
    return {
        "tid": tid, "cl_a": cl_a, "cl_b": cl_b, "cl_c": cl_c,
        "admin": admin_id, "coord": coord_id,
        "viewer": viewer_id, "auditor": auditor_id,
    }


# ────────────────────────────────────────────────────────────────────────
#  Lazy migration: users.client_id legacy → user_scope_assignments
# ────────────────────────────────────────────────────────────────────────
class TestLazyMigration:
    async def test_legacy_client_id_migrates_on_first_request(self, env, http_client, db):
        # En el setup el viewer tiene `users.client_id = cl_a` pero NO hay
        # filas en user_scope_assignments todavía.
        pre = await db.user_scope_assignments.count_documents({
            "user_id": env["viewer"]})
        assert pre == 0

        h = _bearer(user_id=env["viewer"], tenant_id=env["tid"],
                    role="client_viewer", client_id=env["cl_a"],
                    email="viewer@h.io")
        r = await http_client.get("/api/admin/ai/invocation-log", headers=h)
        assert r.status_code == 200

        # Después de UN request, debe existir la fila en user_scope_assignments
        post = await db.user_scope_assignments.count_documents({
            "user_id": env["viewer"], "client_id": env["cl_a"]})
        assert post == 1

    async def test_migration_is_idempotent(self, env, http_client, db):
        h = _bearer(user_id=env["viewer"], tenant_id=env["tid"],
                    role="client_viewer", client_id=env["cl_a"],
                    email="viewer@h.io")
        # 3 requests consecutivas
        for _ in range(3):
            r = await http_client.get("/api/admin/ai/invocation-log", headers=h)
            assert r.status_code == 200
        # Solo debe haber UNA fila — no duplicados
        rows = await db.user_scope_assignments.count_documents({
            "user_id": env["viewer"]})
        assert rows == 1


# ────────────────────────────────────────────────────────────────────────
#  Endpoints CRUD de scopes
# ────────────────────────────────────────────────────────────────────────
class TestScopeCrud:
    async def test_admin_lists_scopes_of_external(self, env, http_client, db):
        # Provocar lazy migration primero
        h_v = _bearer(user_id=env["viewer"], tenant_id=env["tid"],
                      role="client_viewer", client_id=env["cl_a"],
                      email="viewer@h.io")
        await http_client.get("/api/admin/ai/invocation-log", headers=h_v)

        h = _bearer(user_id=env["admin"], tenant_id=env["tid"],
                    role="admin", email="admin@h.io")
        r = await http_client.get(
            f"/api/admin/users/{env['viewer']}/scopes", headers=h)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["count"] == 1
        assert d["items"][0]["client_id"] == env["cl_a"]

    async def test_admin_adds_second_scope(self, env, http_client):
        # Provocar lazy migration primero para que cl_a aparezca
        h_v = _bearer(user_id=env["viewer"], tenant_id=env["tid"],
                      role="client_viewer", client_id=env["cl_a"],
                      email="viewer@h.io")
        await http_client.get("/api/admin/ai/invocation-log", headers=h_v)

        h = _bearer(user_id=env["admin"], tenant_id=env["tid"],
                    role="admin", email="admin@h.io")
        r = await http_client.post(
            f"/api/admin/users/{env['viewer']}/scopes",
            json={"client_id": env["cl_b"]}, headers=h,
        )
        assert r.status_code == 201, r.text
        # Listar
        r2 = await http_client.get(
            f"/api/admin/users/{env['viewer']}/scopes", headers=h)
        assert r2.json()["data"]["count"] == 2

    async def test_add_scope_idempotent(self, env, http_client):
        # Lazy migration
        h_v = _bearer(user_id=env["viewer"], tenant_id=env["tid"],
                      role="client_viewer", client_id=env["cl_a"],
                      email="viewer@h.io")
        await http_client.get("/api/admin/ai/invocation-log", headers=h_v)

        h = _bearer(user_id=env["admin"], tenant_id=env["tid"],
                    role="admin", email="admin@h.io")
        # Add the same client_id twice
        await http_client.post(f"/api/admin/users/{env['viewer']}/scopes",
                                json={"client_id": env["cl_b"]}, headers=h)
        r2 = await http_client.post(f"/api/admin/users/{env['viewer']}/scopes",
                                     json={"client_id": env["cl_b"]}, headers=h)
        assert r2.status_code == 201
        r3 = await http_client.get(
            f"/api/admin/users/{env['viewer']}/scopes", headers=h)
        # cl_a (legacy) + cl_b (idempotente añadido 2 veces) = 2
        assert r3.json()["data"]["count"] == 2

    async def test_add_scope_with_invalid_client_id_fails(self, env, http_client):
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"],
                    role="admin", email="admin@h.io")
        r = await http_client.post(
            f"/api/admin/users/{env['viewer']}/scopes",
            json={"client_id": "00000000-0000-0000-0000-000000000000"},
            headers=h,
        )
        assert r.status_code == 422

    async def test_scopes_only_for_external_roles(self, env, http_client):
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"],
                    role="admin", email="admin@h.io")
        # Intentar añadir scope a un admin (interno) → 422
        r = await http_client.post(
            f"/api/admin/users/{env['admin']}/scopes",
            json={"client_id": env["cl_a"]}, headers=h,
        )
        assert r.status_code == 422

    async def test_delete_last_scope_blocked(self, env, http_client, db):
        # Lazy migration
        h_v = _bearer(user_id=env["viewer"], tenant_id=env["tid"],
                      role="client_viewer", client_id=env["cl_a"],
                      email="viewer@h.io")
        await http_client.get("/api/admin/ai/invocation-log", headers=h_v)

        scope = await db.user_scope_assignments.find_one(
            {"user_id": env["viewer"], "client_id": env["cl_a"]}, {"_id": 0})
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"],
                    role="admin", email="admin@h.io")
        r = await http_client.delete(
            f"/api/admin/users/{env['viewer']}/scopes/{scope['id']}",
            headers=h,
        )
        assert r.status_code == 422
        assert "último scope" in r.json()["errors"][0]["message"].lower()

    async def test_delete_scope_when_multiple_ok(self, env, http_client, db):
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"],
                    role="admin", email="admin@h.io")
        # 1) Provocar lazy migration creando cl_a
        h_v = _bearer(user_id=env["viewer"], tenant_id=env["tid"],
                      role="client_viewer", client_id=env["cl_a"],
                      email="viewer@h.io")
        await http_client.get("/api/admin/ai/invocation-log", headers=h_v)
        # 2) Añadir cl_b
        await http_client.post(
            f"/api/admin/users/{env['viewer']}/scopes",
            json={"client_id": env["cl_b"]}, headers=h)
        # 3) Borrar cl_a (queda cl_b)
        scope_a = await db.user_scope_assignments.find_one(
            {"user_id": env["viewer"], "client_id": env["cl_a"]}, {"_id": 0})
        r = await http_client.delete(
            f"/api/admin/users/{env['viewer']}/scopes/{scope_a['id']}",
            headers=h)
        assert r.status_code == 200
        rows = await db.user_scope_assignments.count_documents({
            "user_id": env["viewer"]})
        assert rows == 1

    async def test_coordinator_can_manage_external_scopes(self, env, http_client):
        # Coordinator puede invitar externos (ASSIGNMENT_RULES de Bundle G+),
        # así que también puede manejar sus scopes.
        h = _bearer(user_id=env["coord"], tenant_id=env["tid"],
                    role="coordinator", email="coord@h.io")
        r = await http_client.post(
            f"/api/admin/users/{env['viewer']}/scopes",
            json={"client_id": env["cl_b"]}, headers=h,
        )
        assert r.status_code == 201

    async def test_coordinator_cannot_manage_admin_scopes(self, env, http_client):
        h = _bearer(user_id=env["coord"], tenant_id=env["tid"],
                    role="coordinator", email="coord@h.io")
        # Aunque admin no debería tener scopes, intentamos por seguridad
        r = await http_client.post(
            f"/api/admin/users/{env['admin']}/scopes",
            json={"client_id": env["cl_a"]}, headers=h,
        )
        # 422 ("interno no maneja scopes") O 403 — ambos aceptables
        assert r.status_code in (403, 422)


# ────────────────────────────────────────────────────────────────────────
#  Multi-scope efectivo en queries
# ────────────────────────────────────────────────────────────────────────
class TestMultiScopeQueries:
    async def test_auditor_with_two_scopes_sees_both(self, env, http_client, db):
        # 1) Lazy migration: auditor ya tiene cl_b
        h_a = _bearer(user_id=env["auditor"], tenant_id=env["tid"],
                      role="client_auditor", client_id=env["cl_b"],
                      email="auditor@h.io")
        await http_client.get("/api/admin/ai/invocation-log", headers=h_a)
        # 2) Admin añade cl_c al scope
        h_ad = _bearer(user_id=env["admin"], tenant_id=env["tid"],
                       role="admin", email="admin@h.io")
        await http_client.post(
            f"/api/admin/users/{env['auditor']}/scopes",
            json={"client_id": env["cl_c"]}, headers=h_ad)
        # 3) Auditor sin pasar client_id → ve cl_b Y cl_c (2 + 1 = 3 invocations)
        r = await http_client.get("/api/admin/ai/invocation-log", headers=h_a)
        items = r.json()["data"]["items"]
        client_ids = {it["client_id"] for it in items}
        assert env["cl_b"] in client_ids
        assert env["cl_c"] in client_ids
        assert env["cl_a"] not in client_ids
        assert len(items) == 3

    async def test_auditor_with_two_scopes_can_filter_by_one(self, env, http_client, db):
        # Setup: auditor tiene cl_b y cl_c
        h_a = _bearer(user_id=env["auditor"], tenant_id=env["tid"],
                      role="client_auditor", client_id=env["cl_b"],
                      email="auditor@h.io")
        await http_client.get("/api/admin/ai/invocation-log", headers=h_a)
        h_ad = _bearer(user_id=env["admin"], tenant_id=env["tid"],
                       role="admin", email="admin@h.io")
        await http_client.post(
            f"/api/admin/users/{env['auditor']}/scopes",
            json={"client_id": env["cl_c"]}, headers=h_ad)
        # Filtrar por cl_c (dentro de scope) → solo cl_c
        r = await http_client.get(
            "/api/admin/ai/invocation-log",
            params={"client_id": env["cl_c"]}, headers=h_a)
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert all(it["client_id"] == env["cl_c"] for it in items)
        assert len(items) == 1

    async def test_auditor_filter_outside_scope_denied(self, env, http_client):
        # Auditor tiene SOLO cl_b. Pedir cl_a (no en scope) → 403
        h_a = _bearer(user_id=env["auditor"], tenant_id=env["tid"],
                      role="client_auditor", client_id=env["cl_b"],
                      email="auditor@h.io")
        r = await http_client.get(
            "/api/admin/ai/invocation-log",
            params={"client_id": env["cl_a"]}, headers=h_a)
        assert r.status_code == 403


# ────────────────────────────────────────────────────────────────────────
#  Delete user revokes scopes
# ────────────────────────────────────────────────────────────────────────
class TestDeleteUserRevokesScopes:
    async def test_soft_delete_user_revokes_all_scopes(self, env, http_client, db):
        # 1) Crear scopes: viewer tiene cl_a (lazy) + cl_b (add)
        h_v = _bearer(user_id=env["viewer"], tenant_id=env["tid"],
                      role="client_viewer", client_id=env["cl_a"],
                      email="viewer@h.io")
        await http_client.get("/api/admin/ai/invocation-log", headers=h_v)
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"],
                    role="admin", email="admin@h.io")
        await http_client.post(
            f"/api/admin/users/{env['viewer']}/scopes",
            json={"client_id": env["cl_b"]}, headers=h)
        assert await db.user_scope_assignments.count_documents({
            "user_id": env["viewer"]}) == 2

        # 2) Soft-delete del user
        r = await http_client.delete(
            f"/api/admin/users/{env['viewer']}", headers=h)
        assert r.status_code == 200
        # 3) Scopes deben estar limpios
        assert await db.user_scope_assignments.count_documents({
            "user_id": env["viewer"]}) == 0
