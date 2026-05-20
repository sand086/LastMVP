"""Iter40 · Bundle G — Hardening de Aislamiento Multi-Cliente.

Cubre los 4 gaps detectados en el audit RBAC:

  G-01  client_id es clampeado al user.client_id para externos en endpoints AI.
  G-02  client_viewer aterriza en /auditor (no /dashboard), CSV export bloqueado.
  G-03  Al crear/actualizar usuario externo, client_id debe existir en el tenant.
  G-04  Cambios de client_id en BD aplican en la siguiente request (refresco).

Endpoints atacados:
  POST   /api/auth/login                          (G-01 — JWT lleva client_id)
  GET    /api/auth/me                             (G-01 — /me devuelve client_id)
  POST   /api/admin/users                         (G-03)
  PATCH  /api/admin/users/{id}                    (G-03 + G-04)
  GET    /api/admin/ai/consumption                (G-01 — clamp)
  GET    /api/admin/ai/cost-trend                 (G-01 — clamp)
  GET    /api/admin/ai/invocation-log             (G-01 — clamp)
  GET    /api/admin/ai/audit/preview              (G-01 — clamp)
  GET    /api/admin/ai/audit/export.csv           (G-01 — gated por _AUDIT_EXPORT_RBAC)
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token, decode_token, hash_password
from core.uuid import new_id


def _bearer(*, user_id: str, tenant_id: str, role: str,
            email: str = "x@t", client_id: str | None = None):
    tok = create_access_token(
        user_id=user_id, tenant_id=tenant_id,
        role=role, email=email, client_id=client_id,
    )
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def env(db):
    """Setup: 1 tenant con 2 clients (A y B) y 4 usuarios:
        - root_dev (interno, ve todo)
        - admin (interno, ve todo)
        - viewer_A (externo, anclado a client A)
        - auditor_B (externo, anclado a client B)
    """
    tid = new_id()
    cl_a = new_id()
    cl_b = new_id()
    root_id = new_id()
    admin_id = new_id()
    viewer_id = new_id()
    auditor_id = new_id()
    now = datetime.now(timezone.utc).isoformat()

    await db.tenants.insert_one({
        "id": tid, "slug": "g-iter40", "name": "T-G", "status": "active",
    })
    await db.clients.insert_many([
        {"id": cl_a, "tenant_id": tid, "name": "Cliente A", "status": "active",
         "ingest_mode": "webhook"},
        {"id": cl_b, "tenant_id": tid, "name": "Cliente B", "status": "active",
         "ingest_mode": "webhook"},
    ])
    pwd_hash = hash_password("Test123!")
    await db.users.insert_many([
        {"id": root_id, "tenant_id": tid, "email": "root@g.io",
         "role": "root_dev", "status": "active", "password_hash": pwd_hash,
         "client_id": None, "created_at": now},
        {"id": admin_id, "tenant_id": tid, "email": "admin@g.io",
         "role": "admin", "status": "active", "password_hash": pwd_hash,
         "client_id": None, "created_at": now},
        {"id": viewer_id, "tenant_id": tid, "email": "viewer@g.io",
         "role": "client_viewer", "status": "active",
         "password_hash": pwd_hash, "client_id": cl_a, "created_at": now},
        {"id": auditor_id, "tenant_id": tid, "email": "auditor@g.io",
         "role": "client_auditor", "status": "active",
         "password_hash": pwd_hash, "client_id": cl_b, "created_at": now},
    ])

    # Sembrar invocation_log para que las queries devuelvan algo "cross-client"
    await db.ai_invocation_log.insert_many([
        {"id": new_id(), "tenant_id": tid, "client_id": cl_a,
         "feature_code": "classify_motivo", "status": "ok",
         "cost_usd": 0.10, "created_at": now},
        {"id": new_id(), "tenant_id": tid, "client_id": cl_a,
         "feature_code": "classify_motivo", "status": "ok",
         "cost_usd": 0.20, "created_at": now},
        {"id": new_id(), "tenant_id": tid, "client_id": cl_b,
         "feature_code": "classify_motivo", "status": "ok",
         "cost_usd": 0.30, "created_at": now},
        {"id": new_id(), "tenant_id": tid, "client_id": cl_b,
         "feature_code": "classify_motivo", "status": "ok",
         "cost_usd": 0.40, "created_at": now},
    ])

    return {
        "tid": tid, "cl_a": cl_a, "cl_b": cl_b,
        "root": root_id, "admin": admin_id,
        "viewer": viewer_id, "auditor": auditor_id,
    }


# ────────────────────────────────────────────────────────────────────────
#  G-01 · client_id en JWT y en /me
# ────────────────────────────────────────────────────────────────────────
class TestG01_JwtAndMe:
    async def test_login_puts_client_id_in_jwt(self, env, http_client):
        r = await http_client.post(
            "/api/auth/login",
            json={"email": "viewer@g.io", "password": "Test123!"},
        )
        assert r.status_code == 200, r.text
        body = r.json()["data"]
        assert body["user"]["client_id"] == env["cl_a"]
        # decode token y validar
        payload = decode_token(body["access_token"])
        assert payload["client_id"] == env["cl_a"]
        assert payload["role"] == "client_viewer"

    async def test_login_internal_user_has_null_client_id(self, env, http_client):
        r = await http_client.post(
            "/api/auth/login",
            json={"email": "admin@g.io", "password": "Test123!"},
        )
        body = r.json()["data"]
        assert body["user"]["client_id"] is None
        payload = decode_token(body["access_token"])
        assert payload.get("client_id") is None

    async def test_me_exposes_client_id(self, env, http_client):
        h = _bearer(user_id=env["viewer"], tenant_id=env["tid"],
                    role="client_viewer", client_id=env["cl_a"],
                    email="viewer@g.io")
        r = await http_client.get("/api/auth/me", headers=h)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["client_id"] == env["cl_a"]
        assert d["default_landing"] == "/auditor"  # G-02


# ────────────────────────────────────────────────────────────────────────
#  G-01 · CLAMP — externo NO puede ver datos de otro client
# ────────────────────────────────────────────────────────────────────────
class TestG01_ClampConsumption:
    async def test_auditor_cannot_query_other_client(self, env, http_client):
        # auditor está anclado a cl_b; intenta pedir cl_a
        # Bundle H — ahora rechaza con 403 (fail-loud), antes era clamp silencioso
        h = _bearer(user_id=env["auditor"], tenant_id=env["tid"],
                    role="client_auditor", client_id=env["cl_b"],
                    email="auditor@g.io")
        r = await http_client.get(
            "/api/admin/ai/invocation-log",
            params={"client_id": env["cl_a"]},  # ◄── intento de bypass
            headers=h,
        )
        assert r.status_code == 403, r.text
        assert "fuera de tu scope" in r.json()["errors"][0]["message"].lower()

    async def test_viewer_cannot_query_other_client_on_cost_trend(self, env, http_client):
        # Bundle H — pedir un client fuera de scope = 403 (no clamp silencioso)
        h = _bearer(user_id=env["viewer"], tenant_id=env["tid"],
                    role="client_viewer", client_id=env["cl_a"],
                    email="viewer@g.io")
        r = await http_client.get(
            "/api/admin/ai/cost-trend",
            params={"client_id": env["cl_b"], "days": 30},  # bypass
            headers=h,
        )
        assert r.status_code == 403, r.text

    async def test_auditor_omitting_param_still_scoped(self, env, http_client):
        # Sin pasar client_id, debe seguir clampeado a cl_b
        h = _bearer(user_id=env["auditor"], tenant_id=env["tid"],
                    role="client_auditor", client_id=env["cl_b"],
                    email="auditor@g.io")
        r = await http_client.get("/api/admin/ai/invocation-log", headers=h)
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 2, f"Esperado 2 invocaciones de cl_b, got {len(items)}"
        assert all(it["client_id"] == env["cl_b"] for it in items)

    async def test_internal_admin_can_query_any_client(self, env, http_client):
        # admin (interno) NO debe ser clampeado: query a cl_a explícito funciona
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"], role="admin",
                    email="admin@g.io")
        r = await http_client.get(
            "/api/admin/ai/invocation-log",
            params={"client_id": env["cl_a"]},
            headers=h,
        )
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 2
        assert all(it["client_id"] == env["cl_a"] for it in items)

    async def test_external_without_client_id_is_denied(self, env, http_client, db):
        # Simular cuenta externa MAL CONFIGURADA (sin client_id)
        bad_id = new_id()
        await db.users.insert_one({
            "id": bad_id, "tenant_id": env["tid"], "email": "bad@g.io",
            "role": "client_viewer", "status": "active",
            "password_hash": hash_password("x"), "client_id": None,
        })
        h = _bearer(user_id=bad_id, tenant_id=env["tid"],
                    role="client_viewer", client_id=None, email="bad@g.io")
        r = await http_client.get("/api/admin/ai/invocation-log", headers=h)
        assert r.status_code == 403, r.text


# ────────────────────────────────────────────────────────────────────────
#  G-02 · landing + CSV export bloqueado para client_viewer
# ────────────────────────────────────────────────────────────────────────
class TestG02_LandingAndExportGate:
    async def test_client_viewer_landing_is_auditor(self, env, http_client):
        r = await http_client.post(
            "/api/auth/login",
            json={"email": "viewer@g.io", "password": "Test123!"},
        )
        body = r.json()["data"]
        assert body["redirect_to"] == "/auditor"

    async def test_client_viewer_cannot_export_csv(self, env, http_client):
        h = _bearer(user_id=env["viewer"], tenant_id=env["tid"],
                    role="client_viewer", client_id=env["cl_a"],
                    email="viewer@g.io")
        r = await http_client.get("/api/admin/ai/audit/export.csv", headers=h)
        assert r.status_code == 403, \
            f"client_viewer NO debería poder exportar CSV firmado, got {r.status_code}"

    async def test_client_auditor_can_export_csv(self, env, http_client):
        h = _bearer(user_id=env["auditor"], tenant_id=env["tid"],
                    role="client_auditor", client_id=env["cl_b"],
                    email="auditor@g.io")
        r = await http_client.get("/api/admin/ai/audit/export.csv", headers=h)
        assert r.status_code == 200, r.text

    async def test_client_viewer_can_read_invocation_log(self, env, http_client):
        h = _bearer(user_id=env["viewer"], tenant_id=env["tid"],
                    role="client_viewer", client_id=env["cl_a"],
                    email="viewer@g.io")
        r = await http_client.get("/api/admin/ai/invocation-log", headers=h)
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert all(it["client_id"] == env["cl_a"] for it in items)


# ────────────────────────────────────────────────────────────────────────
#  G-03 · validar existencia de client_id al crear/editar usuario externo
# ────────────────────────────────────────────────────────────────────────
class TestG03_ClientIdValidation:
    async def test_create_external_with_invalid_client_id_fails(self, env, http_client):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"], role="root_dev",
                    email="root@g.io")
        r = await http_client.post(
            "/api/admin/users",
            json={
                "email": "newviewer@g.io", "name": "New",
                "role": "client_viewer",
                "client_id": "00000000-0000-0000-0000-000000000000",
            },
            headers=h,
        )
        assert r.status_code == 422, r.text
        body = r.json()
        assert "client_id" in (body.get("errors") or [{}])[0].get("message", "").lower() \
            or body.get("errors", [{}])[0].get("field") == "client_id"

    async def test_create_external_without_client_id_fails(self, env, http_client):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"], role="root_dev",
                    email="root@g.io")
        r = await http_client.post(
            "/api/admin/users",
            json={"email": "x@g.io", "name": "X", "role": "client_auditor"},
            headers=h,
        )
        assert r.status_code == 422

    async def test_create_external_with_valid_client_id_ok(self, env, http_client):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"], role="root_dev",
                    email="root@g.io")
        r = await http_client.post(
            "/api/admin/users",
            json={
                "email": "viewer2@g.io", "name": "Viewer 2",
                "role": "client_viewer", "client_id": env["cl_a"],
            },
            headers=h,
        )
        assert r.status_code == 201, r.text
        assert r.json()["data"]["client_id"] == env["cl_a"]

    async def test_create_external_with_cross_tenant_client_id_fails(self, env, http_client, db):
        # Crear un client en OTRO tenant y tratar de asignarlo
        other_tid = new_id()
        other_cl = new_id()
        await db.tenants.insert_one({
            "id": other_tid, "slug": "other-g", "name": "Other", "status": "active",
        })
        await db.clients.insert_one({
            "id": other_cl, "tenant_id": other_tid, "name": "Other CL",
            "status": "active", "ingest_mode": "webhook",
        })
        h = _bearer(user_id=env["root"], tenant_id=env["tid"], role="root_dev",
                    email="root@g.io")
        r = await http_client.post(
            "/api/admin/users",
            json={
                "email": "cross@g.io", "name": "Cross",
                "role": "client_viewer", "client_id": other_cl,
            },
            headers=h,
        )
        assert r.status_code == 422, r.text

    async def test_patch_to_external_with_invalid_client_fails(self, env, http_client):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"], role="root_dev",
                    email="root@g.io")
        r = await http_client.patch(
            f"/api/admin/users/{env['admin']}",
            json={"role": "client_viewer",
                  "client_id": "11111111-1111-1111-1111-111111111111"},
            headers=h,
        )
        assert r.status_code == 422


# ────────────────────────────────────────────────────────────────────────
#  G-04 · refresco de client_id en cada request
# ────────────────────────────────────────────────────────────────────────
class TestG04_ClientIdRefresh:
    async def test_admin_changing_scopes_takes_effect_immediately(self, env, http_client, db):
        """Bundle H · G-04 — cambios en user_scope_assignments aplican sin re-login.

        En Bundle G se cambiaba un campo `users.client_id` (1:1).
        En Bundle H los scopes son aditivos en `user_scope_assignments` (1:N).
        Este test valida que añadir/quitar un scope surte efecto en la
        siguiente request, sin necesidad de re-loguearse.
        """
        # 1. Viewer está en cl_a (vía lazy migration de users.client_id legacy)
        h = _bearer(user_id=env["viewer"], tenant_id=env["tid"],
                    role="client_viewer", client_id=env["cl_a"],
                    email="viewer@g.io")
        r = await http_client.get("/api/admin/ai/invocation-log", headers=h)
        items = r.json()["data"]["items"]
        assert all(it["client_id"] == env["cl_a"] for it in items)

        # 2. Admin añade cl_b al scope del viewer (multi-cliente)
        from core.uuid import new_id
        from datetime import datetime, timezone
        await db.user_scope_assignments.insert_one({
            "id": new_id(), "tenant_id": env["tid"],
            "user_id": env["viewer"], "client_id": env["cl_b"],
            "subclient_id": None, "project_id": None,
            "assigned_by": env["admin"],
            "assigned_at": datetime.now(timezone.utc).isoformat(),
        })

        # 3. SIN re-login, la siguiente request debe ver cl_a Y cl_b (refresco)
        r2 = await http_client.get("/api/admin/ai/invocation-log", headers=h)
        items2 = r2.json()["data"]["items"]
        client_ids_seen = {it["client_id"] for it in items2}
        assert env["cl_a"] in client_ids_seen, \
            "Refresco fail: cl_a desapareció"
        assert env["cl_b"] in client_ids_seen, \
            "Refresco fail: cl_b no se cargó tras añadir scope"
