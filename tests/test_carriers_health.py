"""PROMPT 20 (parcial) — Carrier health & track endpoints transversales.

Estos endpoints viven en `/api/admin/carriers/{id_or_code}/{health|track}` y
despachan al adapter registrado en ADAPTER_REGISTRY. Cubre tanto Routal (real)
como cualquier carrier mock.

  * GET  /admin/carriers/{id|code}/health  → admin+; devuelve estado del adapter
  * POST /admin/carriers/{id|code}/track   → admin+; ejecuta adapter + normalizer
  * RBAC: agent recibe 403
  * Cross-tenant: carrier de otro tenant → 404
  * Mock carriers (fedex/dhl/etc.) → is_mock=true, configured=true
  * Routal (con creds) → is_mock=false, pingable=true (mockeado HTTP)
"""
from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport

from server import app
from core.security import create_access_token
from core.uuid import new_id
from seeds.cae_catalog import run as seed_cae


def _bearer(*, user_id, tenant_id, role="admin"):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_id, tenant_id=tenant_id, role=role, email='ad@t')}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def carriers_setup(db, monkeypatch):
    monkeypatch.setenv("ROUTAL_API_KEY", "test_key")
    monkeypatch.setenv("ROUTAL_PROJECT_ID", "test_project")
    tid = new_id()
    uid_admin, uid_agent = new_id(), new_id()
    fedex_id, routal_id = new_id(), new_id()
    await db.tenants.insert_one({"id": tid, "slug": "ch", "name": "Ch", "status": "active"})
    await db.users.insert_many([
        {"id": uid_admin, "tenant_id": tid, "email": "ad@t",
         "password_hash": "x", "name": "Admin", "role": "admin", "status": "active"},
        {"id": uid_agent, "tenant_id": tid, "email": "ag@t",
         "password_hash": "x", "name": "Ag", "role": "agent", "status": "active"},
    ])
    await db.carriers.insert_many([
        {"id": fedex_id, "tenant_id": tid, "name": "FedEx", "code": "fedex",
         "has_api": True, "active": True, "status": "active"},
        {"id": routal_id, "tenant_id": tid, "name": "Routal", "code": "routal",
         "has_api": True, "active": True, "status": "active"},
    ])
    await seed_cae()
    return {"tenant_id": tid, "admin_id": uid_admin, "agent_id": uid_agent,
            "fedex_id": fedex_id, "routal_id": routal_id}


# ───────────────────────── Health endpoint ────────────────────────────
@pytest.mark.asyncio
async def test_health_mock_carrier_returns_is_mock_true(http_client, carriers_setup):
    s = carriers_setup
    h = _bearer(user_id=s["admin_id"], tenant_id=s["tenant_id"], role="admin")
    r = await http_client.get(f"/api/admin/carriers/{s['fedex_id']}/health", headers=h)
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["code"] == "fedex"
    assert body["has_adapter"] is True
    assert body["is_mock"] is True
    assert body["configured"] is True


@pytest.mark.asyncio
async def test_health_can_use_code_instead_of_id(http_client, carriers_setup):
    s = carriers_setup
    h = _bearer(user_id=s["admin_id"], tenant_id=s["tenant_id"], role="admin")
    # Look up by code "fedex" instead of UUID
    r = await http_client.get("/api/admin/carriers/fedex/health", headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["code"] == "fedex"


@pytest.mark.asyncio
async def test_health_unknown_carrier_returns_404(http_client, carriers_setup):
    s = carriers_setup
    h = _bearer(user_id=s["admin_id"], tenant_id=s["tenant_id"], role="admin")
    r = await http_client.get("/api/admin/carriers/no-such-carrier/health", headers=h)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_health_routal_with_mocked_http(http_client, carriers_setup, monkeypatch):
    """Routal devuelve pingable=true cuando la API responde 200."""
    s = carriers_setup

    class _MockResp:
        status_code = 200
        text = ""
        def json(self): return {"docs": []}

    class _MockClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def get(self, *a, **kw): return _MockResp()
        async def post(self, *a, **kw): return _MockResp()
    import httpx as _httpx
    monkeypatch.setattr(_httpx, "AsyncClient", _MockClient)

    h = _bearer(user_id=s["admin_id"], tenant_id=s["tenant_id"], role="admin")
    r = await http_client.get(f"/api/admin/carriers/{s['routal_id']}/health", headers=h)
    body = r.json()["data"]
    assert body["code"] == "routal"
    assert body["is_mock"] is False
    assert body["pingable"] is True


# ───────────────────────── RBAC + tenant isolation ────────────────────
@pytest.mark.asyncio
async def test_agent_blocked(http_client, carriers_setup):
    s = carriers_setup
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.get(f"/api/admin/carriers/{s['fedex_id']}/health", headers=h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_cross_tenant_isolation(http_client, db, carriers_setup):
    s = carriers_setup
    # Crea otro tenant + admin
    other_tid = new_id()
    other_admin = new_id()
    await db.tenants.insert_one({"id": other_tid, "slug": "ot2", "name": "Ot2", "status": "active"})
    await db.users.insert_one({
        "id": other_admin, "tenant_id": other_tid, "email": "x@y",
        "password_hash": "x", "name": "X", "role": "admin", "status": "active",
    })
    h = _bearer(user_id=other_admin, tenant_id=other_tid, role="admin")
    # Intenta consultar carrier de tenant1 desde tenant2 → 404
    r = await http_client.get(f"/api/admin/carriers/{s['fedex_id']}/health", headers=h)
    assert r.status_code == 404


# ───────────────────────── Track endpoint ─────────────────────────────
@pytest.mark.asyncio
async def test_track_routal_with_mocked_http(http_client, carriers_setup, monkeypatch):
    s = carriers_setup

    class _MockResp:
        status_code = 200
        text = ""
        def json(self):
            return [{
                "id": "stop123", "external_id": "TEST-1",
                "status": "completed", "label": "Test",
                "location": {"lat": 19.4, "lng": -99.1},
                "updated_at": "2026-05-09T00:00:00Z",
            }]
    class _MockClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def post(self, *a, **kw): return _MockResp()
        async def get(self, *a, **kw): return _MockResp()
    import httpx as _httpx
    monkeypatch.setattr(_httpx, "AsyncClient", _MockClient)

    h = _bearer(user_id=s["admin_id"], tenant_id=s["tenant_id"], role="admin")
    r = await http_client.post(f"/api/admin/carriers/routal/track",
                                json={"tracking_id": "TEST-1"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["carrier"]["code"] == "routal"
    assert body["raw"]["raw_code"] == "completed"
    assert body["normalized"]["canonical_status"] == "delivered"
    assert body["normalized"]["is_terminal"] is True


@pytest.mark.asyncio
async def test_track_invalid_tracking_id_returns_422(http_client, carriers_setup):
    s = carriers_setup
    h = _bearer(user_id=s["admin_id"], tenant_id=s["tenant_id"], role="admin")
    r = await http_client.post(f"/api/admin/carriers/fedex/track",
                                json={"tracking_id": ""}, headers=h)
    assert r.status_code == 422
