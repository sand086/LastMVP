"""Iter59 · Admins pueden editar homologaciones CAE.

Bug del usuario: las columnas "Canonical" y "Display" deben ser configurables
por Root/SuperAdmin/Admin. Antes el endpoint estaba limitado a
``require_role("root_dev","superadmin")``.

Cubre:
  - GET  /api/admin/cae/catalog accesible para admin (antes 403)
  - PATCH /api/admin/cae/catalog/{id} accesible para admin
  - coordinator y supervisor siguen denegados
  - El PATCH genera audit log
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id


def _bearer(*, user_id, tenant_id, role, email="u@t.io"):
    tok = create_access_token(
        user_id=user_id, tenant_id=tenant_id, role=role, email=email)
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def env(db):
    t_id = new_id()
    admin_id = new_id()
    coord_id = new_id()
    sup_id = new_id()
    entry_id = new_id()
    await db.tenants.insert_one(
        {"id": t_id, "slug": "t-59", "name": "T-59", "status": "active"})
    await db.users.insert_many([
        {"id": admin_id, "tenant_id": t_id, "email": "ad@t-59.io",
         "role": "admin", "password_hash": "x", "status": "active"},
        {"id": coord_id, "tenant_id": t_id, "email": "co@t-59.io",
         "role": "coordinator", "password_hash": "x", "status": "active"},
        {"id": sup_id, "tenant_id": t_id, "email": "sp@t-59.io",
         "role": "supervisor", "password_hash": "x", "status": "active"},
    ])
    await db.carrier_status_catalog.insert_one({
        "id": entry_id, "tenant_id": None,
        "carrier_id": "routal", "raw_code": "canceled",
        "api_version": "v2", "canonical_status": "cancelled",
        "incident_type": None, "is_terminal": True,
        "requires_action": False, "display_label_es": "Cancelado",
        "confidence": 100, "active": True, "source": "anchor_seed",
    })
    return {
        "tenant_id": t_id, "admin_id": admin_id,
        "coord_id": coord_id, "sup_id": sup_id,
        "entry_id": entry_id,
    }


@pytest.mark.asyncio
async def test_admin_can_list_catalog(http_client, env):
    h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"],
                role="admin")
    r = await http_client.get("/api/admin/cae/catalog", headers=h)
    assert r.status_code == 200
    assert r.json()["success"] is True


@pytest.mark.asyncio
async def test_supervisor_denied(http_client, env):
    h = _bearer(user_id=env["sup_id"], tenant_id=env["tenant_id"],
                role="supervisor")
    r = await http_client.get("/api/admin/cae/catalog", headers=h)
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_coordinator_denied(http_client, env):
    h = _bearer(user_id=env["coord_id"], tenant_id=env["tenant_id"],
                role="coordinator")
    r = await http_client.patch(
        f"/api/admin/cae/catalog/{env['entry_id']}",
        headers=h, json={"canonical_status": "exception"})
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_can_patch_catalog(http_client, db, env):
    h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"],
                role="admin")
    r = await http_client.patch(
        f"/api/admin/cae/catalog/{env['entry_id']}",
        headers=h,
        json={
            "canonical_status": "exception",
            "display_label_es": "Cancelado (excepción)",
            "requires_action": True,
        })
    assert r.status_code == 200, r.text
    payload = r.json()["data"]
    assert payload["canonical_status"] == "exception"
    assert payload["display_label_es"] == "Cancelado (excepción)"
    assert payload["requires_action"] is True

    # DB persisted
    row = await db.carrier_status_catalog.find_one(
        {"id": env["entry_id"]}, {"_id": 0})
    assert row["canonical_status"] == "exception"

    # Audit log
    audit = await db.cae_audit_log.find_one(
        {"entity_id": env["entry_id"], "action": "update"}, {"_id": 0})
    assert audit is not None
    assert audit["before_json"]["canonical_status"] == "cancelled"
    assert audit["after_json"]["canonical_status"] == "exception"


@pytest.mark.asyncio
async def test_admin_patch_nonexistent_404(http_client, env):
    h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"],
                role="admin")
    r = await http_client.patch(
        "/api/admin/cae/catalog/does-not-exist",
        headers=h, json={"canonical_status": "exception"})
    assert r.status_code == 404
