"""Tests para los 3 últimos endpoints implementados:
  - GET /api/admin/security/audit  (root_dev|superadmin only)
  - CRUD /api/saved-filters         (agent+, scope user_id)
  - GET /api/admin/claims/{id}/export.pdf
  - POST /api/admin/claims/bulk-export.zip
"""
from __future__ import annotations

import io
import zipfile

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id


def _bearer(*, user_id: str, tenant_id: str, role: str = "admin",
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
    super_uid = new_id()
    admin_uid = new_id()
    agent_uid = new_id()
    cl_id = new_id()
    await db.tenants.insert_one({"id": tid, "slug": "sec-t", "name": "T",
                                 "status": "active"})
    await db.users.insert_many([
        {"id": super_uid, "tenant_id": tid, "email": "root@t",
         "role": "root_dev", "status": "active"},
        {"id": admin_uid, "tenant_id": tid, "email": "admin@t",
         "role": "admin", "status": "active"},
        {"id": agent_uid, "tenant_id": tid, "email": "ag@t",
         "role": "agent", "status": "active"},
    ])
    await db.clients.insert_one({"id": cl_id, "tenant_id": tid, "name": "C"})
    return {
        "tenant_id": tid, "root_id": super_uid, "admin_id": admin_uid,
        "agent_id": agent_uid, "client_id": cl_id,
    }


# ════════════════════════ Security audit ════════════════════════════════
class TestSecurityAudit:
    async def test_returns_summary_for_root_dev(self, env, http_client):
        h = _bearer(user_id=env["root_id"], tenant_id=env["tenant_id"],
                    role="root_dev")
        r = await http_client.get("/api/admin/security/audit", headers=h)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "checks" in data
        assert "summary" in data
        assert isinstance(data["checks"], list)
        assert len(data["checks"]) >= 8
        assert "ready_for_prod" in data["summary"]
        assert {"pass", "warn", "fail", "total_checks", "ready_for_prod"} <= set(data["summary"])

    async def test_admin_forbidden(self, env, http_client):
        h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"],
                    role="admin")
        r = await http_client.get("/api/admin/security/audit", headers=h)
        assert r.status_code == 403

    async def test_agent_forbidden(self, env, http_client):
        h = _bearer(user_id=env["agent_id"], tenant_id=env["tenant_id"],
                    role="agent")
        r = await http_client.get("/api/admin/security/audit", headers=h)
        assert r.status_code == 403


# ════════════════════════ Saved filters CRUD ════════════════════════════
class TestSavedFilters:
    async def test_create_list_delete_flow(self, env, http_client):
        h = _bearer(user_id=env["agent_id"], tenant_id=env["tenant_id"],
                    role="agent")
        # list inicial vacío
        r = await http_client.get("/api/saved-filters", headers=h)
        assert r.status_code == 200
        assert r.json()["data"]["count"] == 0

        # create
        r = await http_client.post(
            "/api/saved-filters", headers=h,
            json={"name": "Mis abiertos", "scope": "agent_queue",
                  "filters": {"status": "open"}},
        )
        assert r.status_code == 201
        fid = r.json()["data"]["id"]
        assert r.json()["data"]["name"] == "Mis abiertos"
        assert r.json()["data"]["scope"] == "agent_queue"

        # list trae 1
        r = await http_client.get("/api/saved-filters", headers=h)
        assert r.json()["data"]["count"] == 1

        # delete
        r = await http_client.delete(f"/api/saved-filters/{fid}", headers=h)
        assert r.status_code == 200
        assert r.json()["data"]["deleted"] is True

        # list vuelve a 0
        r = await http_client.get("/api/saved-filters", headers=h)
        assert r.json()["data"]["count"] == 0

    async def test_user_isolation(self, env, http_client, db):
        # agent A crea filtro; agent B no lo ve
        h_a = _bearer(user_id=env["agent_id"], tenant_id=env["tenant_id"],
                      role="agent")
        await http_client.post(
            "/api/saved-filters", headers=h_a,
            json={"name": "x", "scope": "agent_queue", "filters": {}},
        )
        # crear segundo agente
        other = new_id()
        await db.users.insert_one({"id": other, "tenant_id": env["tenant_id"],
                                   "email": "b@t", "role": "agent",
                                   "status": "active"})
        h_b = _bearer(user_id=other, tenant_id=env["tenant_id"], role="agent")
        r = await http_client.get("/api/saved-filters", headers=h_b)
        assert r.json()["data"]["count"] == 0

    async def test_delete_unknown_returns_404(self, env, http_client):
        h = _bearer(user_id=env["agent_id"], tenant_id=env["tenant_id"],
                    role="agent")
        r = await http_client.delete("/api/saved-filters/nope-xx", headers=h)
        assert r.status_code == 404

    async def test_client_viewer_forbidden(self, env, http_client, db):
        viewer = new_id()
        await db.users.insert_one({"id": viewer, "tenant_id": env["tenant_id"],
                                   "email": "v@t", "role": "client_viewer",
                                   "status": "active"})
        h = _bearer(user_id=viewer, tenant_id=env["tenant_id"],
                    role="client_viewer")
        r = await http_client.get("/api/saved-filters", headers=h)
        assert r.status_code == 403


# ════════════════════════ Claims PDF ════════════════════════════════════
class TestClaimsPdf:
    async def _seed_claim(self, db, tenant_id, client_id):
        ticket_id = new_id()
        claim_id = new_id()
        await db.tickets.insert_one({
            "id": ticket_id, "tenant_id": tenant_id,
            "client_id": client_id, "status": "open",
            "tracking_id": "TRK-PDF-1", "motivo_codigo": "DAMAGED",
            "created_at": "2026-02-01T10:00:00+00:00",
        })
        await db.claims.insert_one({
            "id": claim_id, "tenant_id": tenant_id,
            "ticket_id": ticket_id, "client_id": client_id,
            "status": "in_review", "tipo": "damage",
            "monto_solicitado": 1500.50, "divisa": "MXN",
            "created_at": "2026-02-01T10:30:00+00:00",
            "updated_at": "2026-02-01T10:30:00+00:00",
        })
        return claim_id, ticket_id

    async def test_individual_claim_pdf(self, env, http_client, db):
        cid, _ = await self._seed_claim(db, env["tenant_id"], env["client_id"])
        h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"],
                    role="admin")
        r = await http_client.get(
            f"/api/admin/claims/{cid}/export.pdf", headers=h,
        )
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:4] == b"%PDF"
        assert f"reclamo-{cid}.pdf" in r.headers.get("content-disposition", "")

    async def test_individual_claim_pdf_not_found(self, env, http_client):
        h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"],
                    role="admin")
        r = await http_client.get(
            "/api/admin/claims/nonexistent/export.pdf", headers=h,
        )
        assert r.status_code == 404

    async def test_individual_claim_pdf_agent_forbidden(self, env, http_client, db):
        cid, _ = await self._seed_claim(db, env["tenant_id"], env["client_id"])
        h = _bearer(user_id=env["agent_id"], tenant_id=env["tenant_id"],
                    role="agent")
        r = await http_client.get(
            f"/api/admin/claims/{cid}/export.pdf", headers=h,
        )
        assert r.status_code == 403

    async def test_bulk_export_zip(self, env, http_client, db):
        c1, _ = await self._seed_claim(db, env["tenant_id"], env["client_id"])
        c2, _ = await self._seed_claim(db, env["tenant_id"], env["client_id"])
        h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"],
                    role="admin")
        r = await http_client.post(
            "/api/admin/claims/bulk-export.zip", headers=h,
            json={"claim_ids": [c1, c2, "nonexistent"]},
        )
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        # validar contenido del zip
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        assert f"reclamo-{c1}.pdf" in names
        assert f"reclamo-{c2}.pdf" in names
        # bulk-count header refleja IDs válidos del tenant (2)
        assert r.headers.get("x-mye-bulk-count") == "2"

    async def test_bulk_export_empty_returns_404(self, env, http_client):
        h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"],
                    role="admin")
        r = await http_client.post(
            "/api/admin/claims/bulk-export.zip", headers=h,
            json={"claim_ids": ["nope-1", "nope-2"]},
        )
        assert r.status_code == 404
