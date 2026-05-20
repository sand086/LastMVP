"""Iter60 · Catálogo CAE manda en ingest + reclasificación retroactiva.

Contexto: el usuario remapeó ``routal/canceled`` de ``cancelled`` a
``exception`` pero las guías existentes ya estaban en ``internal_status=
returned`` por la heurística pre-CAE y no generaban tickets de incidencia.

Cubre:
  - Fix 1: ingest respeta el catálogo CAE para internal_status/is_terminal.
  - Fix 2: endpoint ``POST /admin/cae/catalog/{id}/reclassify`` actualiza
    guías existentes y dispara WorkflowEngine para crear tickets.
  - Fix 3: WorkflowEngine reconoce canonical ∈ {exception,cancelled} como
    incidencia aunque incident_type esté vacío.
  - Idempotencia: re-ejecutar reclassify no duplica tickets.
  - Preview endpoint cuenta correctamente.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id
from services.ingest_service import IngestService


def _bearer(*, user_id, tenant_id, role="admin", email="u@t.io"):
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
    client_id = new_id()
    carrier_id = new_id()
    entry_id = new_id()

    await db.tenants.insert_one(
        {"id": t_id, "slug": "t-60", "name": "T-60", "status": "active"})
    await db.users.insert_one({
        "id": admin_id, "tenant_id": t_id, "email": "ad@t-60.io",
        "role": "admin", "password_hash": "x", "status": "active",
    })
    await db.clients.insert_one({
        "id": client_id, "tenant_id": t_id, "name": "Cli T60",
        "slug": "cli-t60", "status": "active",
    })
    await db.carriers.insert_one({
        "id": carrier_id, "tenant_id": t_id, "code": "routal",
        "name": "Routal", "status": "active",
    })
    # Catálogo: routal/canceled → exception (lo que el user configuró)
    await db.carrier_status_catalog.insert_one({
        "id": entry_id, "tenant_id": None,
        "carrier_id": "routal", "raw_code": "canceled",
        "api_version": "v2", "canonical_status": "exception",
        "incident_type": None, "is_terminal": False,
        "requires_action": True, "display_label_es": "Cancelado (excepción)",
        "confidence": 100, "active": True, "source": "anchor_seed",
    })
    return {
        "tenant_id": t_id, "admin_id": admin_id,
        "client_id": client_id, "carrier_id": carrier_id,
        "entry_id": entry_id,
    }


@pytest.mark.asyncio
async def test_ingest_respects_catalog_for_canceled(db, env):
    """Fix 1 — `process_event` con raw_code='canceled' debe usar el catálogo
    (canonical=exception, is_terminal=False) y NO la heurística vieja
    (canonical=returned, is_terminal=True).
    """
    svc = IngestService(tenant_id=env["tenant_id"])
    outcome = await svc.process_event(
        client_id=env["client_id"], tracking_id="TRK-CANCEL-001",
        carrier_code="routal", carrier_status="canceled",
        raw_code="canceled", api_version="v2", source="pull",
    )
    assert outcome.action == "created"
    guia = await db.guias.find_one(
        {"tenant_id": env["tenant_id"], "tracking_id": "TRK-CANCEL-001"},
        {"_id": 0})
    assert guia["internal_status"] == "exception"
    assert guia["is_terminal"] is False
    # Y debió crear un ticket de incidencia (Fix 3 también verificado)
    ticket = await db.tickets.find_one(
        {"tenant_id": env["tenant_id"], "guia_id": guia["id"]}, {"_id": 0})
    assert ticket is not None
    assert ticket["incident_type"] == "exception"


@pytest.mark.asyncio
async def test_reclassify_preview_counts(http_client, db, env):
    # Sembrar 3 guías con el estado VIEJO (returned/terminal=True)
    for i in range(3):
        await db.guias.insert_one({
            "id": new_id(), "tenant_id": env["tenant_id"],
            "client_id": env["client_id"], "tracking_id": f"OLD-{i}",
            "carrier_code": "routal", "raw_code": "canceled",
            "carrier_status": "canceled", "internal_status": "returned",
            "is_terminal": True, "api_version": "v2",
        })
    h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"])
    r = await http_client.get(
        f"/api/admin/cae/catalog/{env['entry_id']}/reclassify-preview",
        headers=h)
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["total_guias"] == 3
    assert d["needs_change"] == 3
    assert d["target"]["internal_status"] == "exception"
    assert d["target"]["is_terminal"] is False


@pytest.mark.asyncio
async def test_reclassify_updates_and_creates_tickets(http_client, db, env):
    # Sembrar 2 guías legacy
    g_ids = []
    for i in range(2):
        gid = new_id()
        g_ids.append(gid)
        await db.guias.insert_one({
            "id": gid, "tenant_id": env["tenant_id"],
            "client_id": env["client_id"], "tracking_id": f"LEG-{i}",
            "carrier_code": "routal", "raw_code": "canceled",
            "carrier_status": "canceled", "internal_status": "returned",
            "is_terminal": True, "api_version": "v2",
        })
    h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"])
    r = await http_client.post(
        f"/api/admin/cae/catalog/{env['entry_id']}/reclassify",
        headers=h, json={"dry_run": False, "create_tickets": True})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["processed"] == 2
    assert d["updated"] == 2
    assert d["tickets_created"] == 2

    # Verificar estado final
    for gid in g_ids:
        g = await db.guias.find_one({"id": gid}, {"_id": 0})
        assert g["internal_status"] == "exception"
        assert g["is_terminal"] is False
        tk = await db.tickets.find_one(
            {"guia_id": gid, "tenant_id": env["tenant_id"]}, {"_id": 0})
        assert tk is not None
        assert tk["incident_type"] == "exception"

    # Audit log persistido
    audit = await db.cae_audit_log.find_one(
        {"entity_id": env["entry_id"], "action": "reclassify"}, {"_id": 0})
    assert audit is not None


@pytest.mark.asyncio
async def test_reclassify_idempotent(http_client, db, env):
    # Sembrar 1 guía legacy
    gid = new_id()
    await db.guias.insert_one({
        "id": gid, "tenant_id": env["tenant_id"],
        "client_id": env["client_id"], "tracking_id": "IDEM-1",
        "carrier_code": "routal", "raw_code": "canceled",
        "carrier_status": "canceled", "internal_status": "returned",
        "is_terminal": True, "api_version": "v2",
    })
    h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"])
    # Primera corrida
    r1 = await http_client.post(
        f"/api/admin/cae/catalog/{env['entry_id']}/reclassify",
        headers=h, json={"dry_run": False, "create_tickets": True})
    assert r1.json()["data"]["tickets_created"] == 1
    # Segunda corrida — no debe duplicar
    r2 = await http_client.post(
        f"/api/admin/cae/catalog/{env['entry_id']}/reclassify",
        headers=h, json={"dry_run": False, "create_tickets": True})
    d2 = r2.json()["data"]
    assert d2["updated"] == 0
    assert d2["tickets_created"] == 0
    # Sigue habiendo 1 ticket (no 2)
    cnt = await db.tickets.count_documents(
        {"guia_id": gid, "tenant_id": env["tenant_id"]})
    assert cnt == 1


@pytest.mark.asyncio
async def test_reclassify_dry_run(http_client, db, env):
    gid = new_id()
    await db.guias.insert_one({
        "id": gid, "tenant_id": env["tenant_id"],
        "client_id": env["client_id"], "tracking_id": "DRY-1",
        "carrier_code": "routal", "raw_code": "canceled",
        "carrier_status": "canceled", "internal_status": "returned",
        "is_terminal": True, "api_version": "v2",
    })
    h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"])
    r = await http_client.post(
        f"/api/admin/cae/catalog/{env['entry_id']}/reclassify",
        headers=h, json={"dry_run": True, "create_tickets": True})
    assert r.json()["data"]["dry_run"] is True
    # La guía sigue intacta
    g = await db.guias.find_one({"id": gid}, {"_id": 0})
    assert g["internal_status"] == "returned"
    assert g["is_terminal"] is True
