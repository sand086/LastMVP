"""Iter21 — Per-user onboarding tour state.

Verifica:
  * GET  /api/users/me/onboarding              status default + suggested_tour por rol
  * POST /api/users/me/onboarding/complete     marca completed + timestamp
  * POST /api/users/me/onboarding/reset        re-trigger (idempotente)
  * Sin auth (401) y aislamiento por usuario
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id


def _bearer(*, user_id, tenant_id, role, email="u@t"):
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
    await db.tenants.insert_one({"id": tid, "slug": "ob-iter21",
                                 "name": "T", "status": "active"})
    users = {
        "agent": new_id(),
        "admin": new_id(),
        "root": new_id(),
        "viewer": new_id(),
        "auditor": new_id(),
    }
    await db.users.insert_many([
        {"id": users["agent"],   "tenant_id": tid, "email": "agent@t",
         "name": "A", "role": "agent", "status": "active"},
        {"id": users["admin"],   "tenant_id": tid, "email": "admin@t",
         "name": "Ad", "role": "admin", "status": "active"},
        {"id": users["root"],    "tenant_id": tid, "email": "root@t",
         "name": "R", "role": "root_dev", "status": "active"},
        {"id": users["viewer"],  "tenant_id": tid, "email": "v@t",
         "name": "V", "role": "client_viewer", "status": "active"},
        {"id": users["auditor"], "tenant_id": tid, "email": "aud@t",
         "name": "Au", "role": "client_auditor", "status": "active"},
    ])
    return {"tid": tid, **users}


class TestOnboardingStatus:
    async def test_default_not_completed_agent(self, env, http_client):
        h = _bearer(user_id=env["agent"], tenant_id=env["tid"], role="agent")
        r = await http_client.get("/api/users/me/onboarding", headers=h)
        assert r.status_code == 200
        body = r.json()
        d = body["data"]
        assert d["completed"] is False
        assert d["completed_at"] is None
        assert d["role"] == "agent"
        assert d["suggested_tour"] == "agent"

    async def test_suggested_tour_admin(self, env, http_client):
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"], role="admin")
        r = await http_client.get("/api/users/me/onboarding", headers=h)
        assert r.json()["data"]["suggested_tour"] == "admin"

    async def test_suggested_tour_root_dev(self, env, http_client):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"], role="root_dev")
        r = await http_client.get("/api/users/me/onboarding", headers=h)
        assert r.json()["data"]["suggested_tour"] == "root_dev"

    async def test_suggested_tour_client_viewer_falls_back_to_agent(self, env, http_client):
        # client_viewer/auditor map to "agent" tour (best fit in MVP).
        h = _bearer(user_id=env["viewer"], tenant_id=env["tid"], role="client_viewer")
        r = await http_client.get("/api/users/me/onboarding", headers=h)
        assert r.json()["data"]["suggested_tour"] == "agent"

    async def test_status_requires_auth(self, http_client):
        r = await http_client.get("/api/users/me/onboarding")
        assert r.status_code == 401


class TestOnboardingComplete:
    async def test_complete_persists(self, env, http_client, db):
        h = _bearer(user_id=env["agent"], tenant_id=env["tid"], role="agent")
        r = await http_client.post("/api/users/me/onboarding/complete", headers=h)
        assert r.status_code == 200
        assert r.json()["data"]["completed"] is True

        # The DB doc now has the flag + iso timestamp
        doc = await db.users.find_one({"id": env["agent"]}, {"_id": 0})
        assert doc["onboarding_completed"] is True
        assert "onboarding_completed_at" in doc
        assert isinstance(doc["onboarding_completed_at"], str)

        # Next GET reflects completion
        r2 = await http_client.get("/api/users/me/onboarding", headers=h)
        d = r2.json()["data"]
        assert d["completed"] is True
        assert d["completed_at"]

    async def test_complete_is_idempotent(self, env, http_client, db):
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"], role="admin")
        r1 = await http_client.post("/api/users/me/onboarding/complete", headers=h)
        first_ts = (await db.users.find_one({"id": env["admin"]}))["onboarding_completed_at"]
        r2 = await http_client.post("/api/users/me/onboarding/complete", headers=h)
        assert r1.status_code == r2.status_code == 200
        # Timestamp is refreshed on each call — but flag remains true and
        # the operation never raises.
        doc = await db.users.find_one({"id": env["admin"]})
        assert doc["onboarding_completed"] is True
        assert doc["onboarding_completed_at"] >= first_ts

    async def test_complete_requires_auth(self, http_client):
        r = await http_client.post("/api/users/me/onboarding/complete")
        assert r.status_code == 401


class TestOnboardingReset:
    async def test_reset_clears_flag(self, env, http_client, db):
        h = _bearer(user_id=env["agent"], tenant_id=env["tid"], role="agent")
        await http_client.post("/api/users/me/onboarding/complete", headers=h)
        r = await http_client.post("/api/users/me/onboarding/reset", headers=h)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["completed"] is False
        assert d["suggested_tour"] == "agent"

        doc = await db.users.find_one({"id": env["agent"]})
        assert doc["onboarding_completed"] is False
        assert "onboarding_completed_at" not in doc

    async def test_reset_unsets_timestamp(self, env, http_client, db):
        h = _bearer(user_id=env["root"], tenant_id=env["tid"], role="root_dev")
        await http_client.post("/api/users/me/onboarding/complete", headers=h)
        await http_client.post("/api/users/me/onboarding/reset", headers=h)
        # After reset, GET shows completed=false, completed_at=null
        r = await http_client.get("/api/users/me/onboarding", headers=h)
        d = r.json()["data"]
        assert d["completed"] is False
        assert d["completed_at"] is None


class TestOnboardingIsolation:
    async def test_user_isolation(self, env, http_client, db):
        # Marking agent as complete doesn't affect admin
        ha = _bearer(user_id=env["agent"], tenant_id=env["tid"], role="agent")
        hb = _bearer(user_id=env["admin"], tenant_id=env["tid"], role="admin")
        await http_client.post("/api/users/me/onboarding/complete", headers=ha)
        rb = await http_client.get("/api/users/me/onboarding", headers=hb)
        assert rb.json()["data"]["completed"] is False
