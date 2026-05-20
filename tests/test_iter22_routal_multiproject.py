"""Iter22 — Routal multi-project per-client refactor.

Cubrir:
  * RoutalAdapter constructor-based (api_key/project_ids/base_url args)
  * ClientRepository.set/get/delete_carrier_config con cifrado Fernet
  * Endpoints REST /api/admin/clients/{id}/carriers/{code}
  * Pull scheduler itera múltiples projects y persiste routal_project_id
    en guias.carrier_meta
  * send_instruction usa el project_id de carrier_meta (1:1)
  * Cross-tenant isolation
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id
from core.crypto import decrypt
from repositories.clients import ClientRepository
from services.cae.adapters.routal import RoutalAdapter


def _bearer(*, user_id, tenant_id, role="admin"):
    tok = create_access_token(user_id=user_id, tenant_id=tenant_id,
                              role=role, email=f"{user_id[:6]}@t")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def env(db):
    tid = new_id()
    other_tid = new_id()
    admin_id = new_id()
    other_admin_id = new_id()
    project_id = new_id()
    client_id = new_id()
    other_client_id = new_id()
    await db.tenants.insert_many([
        {"id": tid, "slug": "cubbo", "name": "Cubbo", "status": "active"},
        {"id": other_tid, "slug": "other", "name": "Other", "status": "active"},
    ])
    await db.users.insert_many([
        {"id": admin_id, "tenant_id": tid, "email": "ad@cubbo",
         "role": "admin", "status": "active"},
        {"id": other_admin_id, "tenant_id": other_tid, "email": "ad@other",
         "role": "admin", "status": "active"},
    ])
    await db.projects.insert_one({"id": project_id, "tenant_id": tid,
                                    "name": "P1", "status": "active"})
    await db.clients.insert_many([
        {"id": client_id, "tenant_id": tid, "project_id": project_id,
         "name": "Cubbo MX", "ingest_mode": "pulling",
         "preferred_carrier_code": "routal", "carriers": {}},
        {"id": other_client_id, "tenant_id": other_tid,
         "name": "Other client", "ingest_mode": "webhook", "carriers": {}},
    ])
    return {
        "tid": tid, "other_tid": other_tid,
        "admin": admin_id, "other_admin": other_admin_id,
        "client_id": client_id, "other_client_id": other_client_id,
    }


# ─── 1) Adapter constructor-based ───────────────────────────────────────
class TestAdapterConstructor:
    def test_constructor_with_args(self):
        a = RoutalAdapter(api_key="K-123", project_ids=["p1", "p2"],
                          base_url="https://custom.routal.test")
        assert a.api_key == "K-123"
        assert a.project_ids == ["p1", "p2"]
        assert a.base_url == "https://custom.routal.test"
        assert a.default_project_id == "p1"

    def test_constructor_dedupes_empty_projects(self):
        a = RoutalAdapter(api_key="K", project_ids=["p1", "", "p2"])
        assert a.project_ids == ["p1", "p2"]

    def test_constructor_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("ROUTAL_API_KEY", "env-key")
        monkeypatch.setenv("ROUTAL_PROJECT_ID", "env-proj")
        a = RoutalAdapter()
        assert a.api_key == "env-key"
        assert a.project_ids == ["env-proj"]

    def test_constructor_no_env_no_args(self, monkeypatch):
        monkeypatch.delenv("ROUTAL_API_KEY", raising=False)
        monkeypatch.delenv("ROUTAL_PROJECT_ID", raising=False)
        a = RoutalAdapter()
        assert a.api_key == ""
        assert a.project_ids == []
        assert a.default_project_id is None


# ─── 2) Repository: set/get/delete carrier config ─────────────────────
class TestRepoCarrierConfig:
    async def test_set_and_get_encrypts_api_key(self, env, db):
        repo = ClientRepository(tenant_id=env["tid"])
        cfg_public = await repo.set_carrier_config(env["client_id"], "routal", {
            "api_key": "SECRET-KEY-XYZ",
            "project_ids": ["pA", "pB"],
            "default_project_id": "pA",
            "base_url": "https://api.routal.com",
            "enabled": True,
        })
        # Public view never leaks the key
        assert "api_key" not in cfg_public
        assert "api_key_ref" not in cfg_public
        assert cfg_public["api_key_set"] is True
        assert cfg_public["project_ids"] == ["pA", "pB"]

        # DB has it encrypted (Fernet token starts with gAAAA...)
        doc = await db.clients.find_one({"id": env["client_id"]}, {"_id": 0})
        ref = doc["carriers"]["routal"]["api_key_ref"]
        assert ref.startswith("gAAAA")
        assert decrypt(ref) == "SECRET-KEY-XYZ"

        # In-use config returns the plaintext for the adapter
        usable = await repo.get_carrier_config(env["client_id"], "routal")
        assert usable["api_key"] == "SECRET-KEY-XYZ"
        assert usable["project_ids"] == ["pA", "pB"]
        assert usable["default_project_id"] == "pA"

    async def test_set_appends_default_to_project_ids(self, env):
        repo = ClientRepository(tenant_id=env["tid"])
        # default_project_id NOT yet in project_ids should be auto-included
        cfg = await repo.set_carrier_config(env["client_id"], "routal", {
            "api_key": "K", "project_ids": ["pX"], "default_project_id": "pY",
        })
        assert "pY" in cfg["project_ids"]
        assert "pX" in cfg["project_ids"]

    async def test_partial_update_preserves_key(self, env, db):
        repo = ClientRepository(tenant_id=env["tid"])
        await repo.set_carrier_config(env["client_id"], "routal", {
            "api_key": "FIRST", "project_ids": ["pA"],
        })
        # Patch only project_ids; api_key must remain
        await repo.set_carrier_config(env["client_id"], "routal", {
            "project_ids": ["pA", "pB"],
        })
        usable = await repo.get_carrier_config(env["client_id"], "routal")
        assert usable["api_key"] == "FIRST"
        assert usable["project_ids"] == ["pA", "pB"]

    async def test_disabled_returns_none(self, env):
        repo = ClientRepository(tenant_id=env["tid"])
        await repo.set_carrier_config(env["client_id"], "routal", {
            "api_key": "K", "project_ids": ["p1"], "enabled": False,
        })
        usable = await repo.get_carrier_config(env["client_id"], "routal")
        assert usable is None

    async def test_delete(self, env, db):
        repo = ClientRepository(tenant_id=env["tid"])
        await repo.set_carrier_config(env["client_id"], "routal", {
            "api_key": "K", "project_ids": ["p1"],
        })
        await repo.delete_carrier_config(env["client_id"], "routal")
        usable = await repo.get_carrier_config(env["client_id"], "routal")
        assert usable is None
        doc = await db.clients.find_one({"id": env["client_id"]}, {"_id": 0})
        assert "routal" not in (doc.get("carriers") or {})


# ─── 3) REST endpoints ──────────────────────────────────────────────────
class TestRESTEndpoints:
    async def test_get_empty_returns_unconfigured(self, env, http_client):
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"])
        r = await http_client.get(
            f"/api/admin/clients/{env['client_id']}/carriers/routal", headers=h)
        assert r.status_code == 200
        assert r.json()["data"]["configured"] is False

    async def test_put_creates_config(self, env, http_client, db):
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"])
        r = await http_client.put(
            f"/api/admin/clients/{env['client_id']}/carriers/routal",
            headers=h, json={
                "api_key": "K-FROM-API",
                "project_ids": ["pAlpha", "pBeta"],
                "default_project_id": "pAlpha",
                "enabled": True,
            })
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["configured"] is True
        assert data["api_key_set"] is True
        assert "api_key" not in data
        assert data["project_ids"] == ["pAlpha", "pBeta"]

        # Subsequent GET reflects it
        g = await http_client.get(
            f"/api/admin/clients/{env['client_id']}/carriers/routal", headers=h)
        assert g.json()["data"]["api_key_set"] is True

    async def test_put_invalid_project_ids_rejected(self, env, http_client):
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"])
        # 51 project_ids → rejection by Pydantic
        r = await http_client.put(
            f"/api/admin/clients/{env['client_id']}/carriers/routal",
            headers=h, json={"project_ids": [f"p{i}" for i in range(51)]})
        assert r.status_code in (400, 422)

    async def test_delete(self, env, http_client):
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"])
        await http_client.put(
            f"/api/admin/clients/{env['client_id']}/carriers/routal",
            headers=h, json={"api_key": "k", "project_ids": ["p1"]})
        r = await http_client.delete(
            f"/api/admin/clients/{env['client_id']}/carriers/routal", headers=h)
        assert r.status_code == 200
        assert r.json()["data"]["deleted"] is True

    async def test_cross_tenant_404(self, env, http_client):
        # other-tenant admin tries to read Cubbo's client → 404
        h = _bearer(user_id=env["other_admin"], tenant_id=env["other_tid"])
        r = await http_client.get(
            f"/api/admin/clients/{env['client_id']}/carriers/routal", headers=h)
        assert r.status_code == 404

    async def test_agent_role_forbidden(self, env, http_client, db):
        agent_id = new_id()
        await db.users.insert_one({"id": agent_id, "tenant_id": env["tid"],
                                     "email": "a@t", "role": "agent",
                                     "status": "active"})
        h = _bearer(user_id=agent_id, tenant_id=env["tid"], role="agent")
        r = await http_client.put(
            f"/api/admin/clients/{env['client_id']}/carriers/routal",
            headers=h, json={"api_key": "k"})
        assert r.status_code == 403


# ─── 4) Scheduler iterates multi-project + persists carrier_meta ──────
class TestSchedulerMultiProject:
    async def test_pull_iterates_all_projects(self, env, db, monkeypatch):
        repo = ClientRepository(tenant_id=env["tid"])
        await repo.set_carrier_config(env["client_id"], "routal", {
            "api_key": "K", "project_ids": ["proj-north", "proj-south"],
            "default_project_id": "proj-north",
        })
        # Ensure carrier exists
        await db.carriers.insert_one({
            "id": new_id(), "tenant_id": env["tid"],
            "code": "routal", "name": "Routal", "status": "active",
            "has_api": True,
        })

        from services.cae.adapters import routal as routal_mod

        seen_project_ids: list[str] = []

        async def fake_plans(self, *, project_id=None, limit=10):
            seen_project_ids.append(project_id)
            if project_id == "proj-north":
                return [{"id": "plan-n1"}]
            if project_id == "proj-south":
                return [{"id": "plan-s1"}]
            return []

        async def fake_stops(self, plan_id):
            if plan_id == "plan-n1":
                return [{"id": "stop-a", "external_id": "TRK-N1",
                         "status": "pending",
                         "updated_at": "2026-05-09T10:00:00Z"}]
            if plan_id == "plan-s1":
                return [{"id": "stop-b", "external_id": "TRK-S1",
                         "status": "completed",
                         "updated_at": "2026-05-09T10:05:00Z"}]
            return []

        monkeypatch.setattr(routal_mod.RoutalAdapter, "list_recent_plans", fake_plans)
        monkeypatch.setattr(routal_mod.RoutalAdapter, "list_stops_in_plan", fake_stops)

        from services.scheduler import _pull_routal
        metrics = await _pull_routal(tenant_id=env["tid"],
                                       client_id=env["client_id"],
                                       limit_plans=5)
        assert metrics["projects"] == ["proj-north", "proj-south"]
        assert metrics["processed"] == 2  # 1 stop per project
        assert seen_project_ids == ["proj-north", "proj-south"]

        # Both guías persisted with carrier_meta.routal_project_id
        g1 = await db.guias.find_one({"tracking_id": "TRK-N1"}, {"_id": 0})
        g2 = await db.guias.find_one({"tracking_id": "TRK-S1"}, {"_id": 0})
        assert g1["carrier_meta"]["routal_project_id"] == "proj-north"
        assert g2["carrier_meta"]["routal_project_id"] == "proj-south"
        assert g2["is_terminal"] is True  # completed → terminal


# ─── 5) send_instruction targets correct project_id ───────────────────
class TestSendInstructionProjectScoped:
    async def test_send_uses_payload_project_id(self, monkeypatch):
        """Adapter must call _search_stop_by_external_id with the project_id
        passed in payload, not the default. This is the 1:1 update path."""
        adapter = RoutalAdapter(api_key="K",
                                  project_ids=["default-proj", "other-proj"])

        called_with: dict[str, str | None] = {"project_id": None}

        async def fake_find(self, tracking_id, *, project_id):
            called_with["project_id"] = project_id
            return {"id": "stop-xyz", "_routal_project_id": project_id}

        async def fake_put(*args, **kwargs):
            # httpx.AsyncClient.put — return a stub response
            class R:
                status_code = 200
            return R()

        monkeypatch.setattr(RoutalAdapter, "_search_stop_by_external_id", fake_find)

        import httpx
        async def fake_request(self, method, url, **kw):
            class R:
                status_code = 200
            return R()
        monkeypatch.setattr(httpx.AsyncClient, "put", fake_put)

        res = await adapter.send_instruction("TRK-1", {
            "status": "canceled",
            "project_id": "other-proj",
            "comments": "Cancelado desde MyE",
        })
        assert res.received is True
        assert called_with["project_id"] == "other-proj"

    async def test_send_falls_back_to_default_project(self, monkeypatch):
        adapter = RoutalAdapter(api_key="K", project_ids=["d1", "d2"])
        called_with: dict[str, str | None] = {"project_id": None}

        async def fake_find(self, tracking_id, *, project_id):
            called_with["project_id"] = project_id
            return {"id": "s", "_routal_project_id": project_id}

        async def fake_put(*args, **kwargs):
            class R: status_code = 200
            return R()

        monkeypatch.setattr(RoutalAdapter, "_search_stop_by_external_id", fake_find)
        import httpx
        monkeypatch.setattr(httpx.AsyncClient, "put", fake_put)

        await adapter.send_instruction("TRK", {"status": "completed"})
        assert called_with["project_id"] == "d1"  # default

    async def test_send_rejects_unknown_status(self):
        adapter = RoutalAdapter(api_key="K", project_ids=["p1"])
        res = await adapter.send_instruction("TRK", {"status": "BOGUS"})
        assert res.received is False
        assert res.status == 400
