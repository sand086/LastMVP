"""PROMPT_27 — Tests del rol read-only `client_auditor`.

El auditor:
  - Puede leer /api/admin/ai/audit/preview, /audit/export.csv,
    /invocation-log y /consumption (tenant-scoped).
  - NO puede tocar features/brackets/client-config (escritura).
  - NO puede entrar al panel operativo (tickets, agente, dashboard,
    jerarquía, catálogo).
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id
from middleware.rbac import ROLE_RANK, default_landing_for
from repositories.ai import AIInvocationLogRepository
from seeds.ai_catalog import run as seed_ai


def _bearer(*, user_id: str, tenant_id: str, role: str = "client_auditor",
            email: str = "auditor@t", client_id: str | None = None):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_id, tenant_id=tenant_id, role=role, email=email, client_id=client_id)}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def auditor_setup(db):
    await seed_ai()
    tid = new_id()
    auditor_uid = new_id()
    admin_uid = new_id()
    cl_id = new_id()
    await db.tenants.insert_one({"id": tid, "slug": "auditor-t", "name": "T",
                                 "status": "active"})
    await db.users.insert_many([
        {"id": auditor_uid, "tenant_id": tid, "email": "auditor@t",
         "role": "client_auditor", "status": "active", "client_id": cl_id},
        {"id": admin_uid, "tenant_id": tid, "email": "admin@t",
         "role": "admin", "status": "active"},
    ])
    await db.clients.insert_one({"id": cl_id, "tenant_id": tid, "name": "C"})
    # 1 invocación de muestra para que el CSV no esté vacío
    repo = AIInvocationLogRepository(tenant_id=tid)
    await repo.append({
        "client_id": cl_id, "user_id": admin_uid,
        "feature_id": "f1", "feature_code": "classify_motivo",
        "ticket_id": None, "provider": "anthropic", "model": "haiku",
        "input_tokens": 100, "output_tokens": 5,
        "cost_usd": 0.001, "cost_mxn": 0.018, "exchange_rate": 17.5,
        "latency_ms": 50, "prompt_hash": "h",
        "prompt_masked_preview": "p", "response_hash": "r",
        "status": "success", "error_code": None,
        "request_id": new_id(),
    })
    return {"tenant_id": tid, "auditor_user_id": auditor_uid,
            "admin_user_id": admin_uid, "client_id": cl_id}


# ════════════════════════ Estructura del rol ════════════════════════════
class TestRoleRegistration:
    def test_role_present_in_rank(self):
        assert "client_auditor" in ROLE_RANK
        # Rank igual o por debajo de client_viewer (no escala privilegios)
        assert ROLE_RANK["client_auditor"] <= ROLE_RANK["client_viewer"]

    def test_default_landing_is_auditor_panel(self):
        assert default_landing_for("client_auditor") == "/auditor"


# ════════════════════════ Acceso permitido ═══════════════════════════════
class TestAuditorReadAccess:
    async def test_can_preview_audit_csv(self, auditor_setup, http_client):
        h = _bearer(user_id=auditor_setup["auditor_user_id"],
                    tenant_id=auditor_setup["tenant_id"])
        r = await http_client.get("/api/admin/ai/audit/preview", headers=h)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["signature"].startswith("sha256=")
        assert d["rows"] >= 1

    async def test_can_download_signed_csv(self, auditor_setup, http_client):
        h = _bearer(user_id=auditor_setup["auditor_user_id"],
                    tenant_id=auditor_setup["tenant_id"])
        r = await http_client.get("/api/admin/ai/audit/export.csv", headers=h)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert "X-MyE-Audit-Signature" in r.headers
        assert r.headers["X-MyE-Audit-Signature"].startswith("sha256=")
        assert int(r.headers["X-MyE-Audit-Rows"]) >= 1

    async def test_can_list_invocation_log(self, auditor_setup, http_client):
        h = _bearer(user_id=auditor_setup["auditor_user_id"],
                    tenant_id=auditor_setup["tenant_id"])
        r = await http_client.get("/api/admin/ai/invocation-log", headers=h)
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) >= 1
        assert items[0]["status"] == "success"

    async def test_can_view_consumption_dashboard(self, auditor_setup, http_client):
        h = _bearer(user_id=auditor_setup["auditor_user_id"],
                    tenant_id=auditor_setup["tenant_id"])
        r = await http_client.get("/api/admin/ai/consumption", headers=h)
        assert r.status_code == 200
        # Estructura mínima
        assert "items" in r.json()["data"]


# ════════════════════════ Acceso denegado ════════════════════════════════
class TestAuditorWriteDenied:
    async def test_cannot_create_feature(self, auditor_setup, http_client):
        h = _bearer(user_id=auditor_setup["auditor_user_id"],
                    tenant_id=auditor_setup["tenant_id"])
        r = await http_client.post("/api/admin/ai/features", headers=h, json={
            "feature_code": "x", "feature_name": "X",
            "recommended_model": "claude-haiku-4-5-20250929",
            "recommended_provider": "anthropic",
            "avg_input_tokens": 1, "avg_output_tokens": 1, "avg_cost_usd": 0.001,
            "destinatario": "agent_internal",
        })
        assert r.status_code in (401, 403)

    async def test_cannot_upsert_client_config(self, auditor_setup, http_client):
        h = _bearer(user_id=auditor_setup["auditor_user_id"],
                    tenant_id=auditor_setup["tenant_id"])
        r = await http_client.put("/api/admin/ai/client-config", headers=h, json={
            "client_id": auditor_setup["client_id"], "is_active": False,
            "enabled_features": [],
        })
        assert r.status_code in (401, 403)

    async def test_cannot_run_benchmark(self, auditor_setup, http_client):
        h = _bearer(user_id=auditor_setup["auditor_user_id"],
                    tenant_id=auditor_setup["tenant_id"])
        r = await http_client.post(
            "/api/admin/ai/benchmark/run?dry_run=true", headers=h,
        )
        assert r.status_code in (401, 403)

    async def test_cannot_invoke_ai(self, auditor_setup, http_client):
        h = _bearer(user_id=auditor_setup["auditor_user_id"],
                    tenant_id=auditor_setup["tenant_id"])
        r = await http_client.post("/api/ai/invoke", headers=h, json={
            "feature_code": "classify_motivo",
            "input": {"client_id": auditor_setup["client_id"], "text": "x"},
        })
        # require_min_role("agent") rechaza al auditor (rank=1 < 2)
        assert r.status_code in (401, 403)


# ════════════════════════ Operaciones bloqueadas ═════════════════════════
class TestAuditorOperationalDenied:
    async def test_cannot_list_admin_tickets(self, auditor_setup, http_client):
        h = _bearer(user_id=auditor_setup["auditor_user_id"],
                    tenant_id=auditor_setup["tenant_id"])
        r = await http_client.get("/api/admin/tickets", headers=h)
        assert r.status_code in (401, 403)

    async def test_cannot_access_agent_queue(self, auditor_setup, http_client):
        h = _bearer(user_id=auditor_setup["auditor_user_id"],
                    tenant_id=auditor_setup["tenant_id"])
        r = await http_client.get("/api/agent/queue", headers=h)
        assert r.status_code in (401, 403)

    async def test_cannot_list_projects(self, auditor_setup, http_client):
        h = _bearer(user_id=auditor_setup["auditor_user_id"],
                    tenant_id=auditor_setup["tenant_id"])
        r = await http_client.get("/api/admin/projects", headers=h)
        assert r.status_code in (401, 403)

    async def test_cannot_list_motivos(self, auditor_setup, http_client):
        h = _bearer(user_id=auditor_setup["auditor_user_id"],
                    tenant_id=auditor_setup["tenant_id"])
        r = await http_client.get("/api/admin/motivos", headers=h)
        assert r.status_code in (401, 403)


# ════════════════════════ Cross-tenant ═══════════════════════════════════
class TestAuditorCrossTenant:
    async def test_audit_csv_only_sees_own_tenant(self, auditor_setup, http_client, db):
        # Crear tenant B con su propio log
        tid_b = new_id()
        await db.tenants.insert_one({"id": tid_b, "slug": "other",
                                     "name": "Other", "status": "active"})
        cl_b = new_id()
        await db.clients.insert_one({"id": cl_b, "tenant_id": tid_b,
                                     "name": "ClB"})
        repo_b = AIInvocationLogRepository(tenant_id=tid_b)
        # 5 invocaciones en B
        for _ in range(5):
            await repo_b.append({
                "client_id": cl_b, "user_id": None,
                "feature_id": "f", "feature_code": "classify_motivo",
                "ticket_id": None, "provider": "anthropic", "model": "haiku",
                "input_tokens": 1, "output_tokens": 1,
                "cost_usd": 0.001, "cost_mxn": 0, "exchange_rate": 17.5,
                "latency_ms": 1, "prompt_hash": "h",
                "prompt_masked_preview": "p", "response_hash": "r",
                "status": "success", "error_code": None,
                "request_id": new_id(),
            })

        h = _bearer(user_id=auditor_setup["auditor_user_id"],
                    tenant_id=auditor_setup["tenant_id"])
        r = await http_client.get("/api/admin/ai/audit/export.csv", headers=h)
        assert r.status_code == 200
        # El auditor de tenant A NO debe ver las 5 filas de tenant B
        assert int(r.headers["X-MyE-Audit-Rows"]) == 1


# ════════════════════════ Login ═══════════════════════════════════════════
class TestAuditorLogin:
    async def test_login_returns_redirect_to_auditor_panel(
        self, auditor_setup, http_client, db,
    ):
        # Crear password hash para auditor
        from core.security import hash_password
        await db.users.update_one(
            {"id": auditor_setup["auditor_user_id"]},
            {"$set": {"password_hash": hash_password("Admin123!")}},
        )
        r = await http_client.post("/api/auth/login", json={
            "email": "auditor@t", "password": "Admin123!",
        })
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["user"]["role"] == "client_auditor"
        assert d["redirect_to"] == "/auditor"
