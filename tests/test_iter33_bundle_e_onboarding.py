"""Iter33 — Bundle E · Onboarding Admin Wizard.

Cobertura:
  * Persistencia per user×tenant
  * Auto-open: admin/superadmin + tenant <30d → true; otros → false
  * Advance / skip-step / complete
  * Pasos mandatorios (welcome, catalog) no se pueden saltar
  * pre_completed_by_tenant detecta cliente/catálogo previos (2do admin)
  * seed-mx-catalog idempotente (12 motivos + 18 soluciones)
  * Avance siguiente paso respeta pasos pre-completados
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id


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
    user_id = new_id()
    now = datetime.now(timezone.utc)
    await db.tenants.insert_one({
        "id": tid, "slug": f"t-{tid[:6]}", "name": "T1", "status": "active",
        "created_at": now.isoformat(),
    })
    await db.users.insert_one({
        "id": user_id, "tenant_id": tid, "email": "a@t",
        "role": "admin", "status": "active",
    })
    return {"tid": tid, "user_id": user_id, "db": db}


# ──────────────────────────────────────────────────────────────────────
# Auto-open logic (E1.1)
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auto_open_for_admin_in_new_tenant(env, http_client):
    """Admin + tenant <30d + sin completed → should_auto_open=True."""
    h = _bearer(user_id=env["user_id"], tenant_id=env["tid"], role="admin")
    r = await http_client.get("/api/admin/onboarding/state", headers=h)
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["should_auto_open"] is True
    assert body["is_completed"] is False
    assert body["in_progress"] is False  # no doc todavía


@pytest.mark.asyncio
async def test_auto_open_false_for_old_tenant(env, http_client):
    """Tenant >30d → should_auto_open=False."""
    db = env["db"]
    old = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    await db.tenants.update_one({"id": env["tid"]}, {"$set": {"created_at": old}})
    h = _bearer(user_id=env["user_id"], tenant_id=env["tid"], role="admin")
    r = await http_client.get("/api/admin/onboarding/state", headers=h)
    assert r.json()["data"]["should_auto_open"] is False


@pytest.mark.asyncio
async def test_auto_open_false_for_agent_role(env, http_client):
    """Rol agent NO ve auto-open (solo admin/superadmin/root_dev)."""
    db = env["db"]
    aid = new_id()
    await db.users.insert_one({
        "id": aid, "tenant_id": env["tid"], "email": "ag@t",
        "role": "agent", "status": "active",
    })
    h = _bearer(user_id=aid, tenant_id=env["tid"], role="agent")
    # Agent no tiene acceso al endpoint /api/admin/onboarding/state → 403
    r = await http_client.get("/api/admin/onboarding/state", headers=h)
    assert r.status_code == 403


# ──────────────────────────────────────────────────────────────────────
# Advance + skip + complete
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_advance_persists_step_data_and_moves_forward(env, http_client):
    h = _bearer(user_id=env["user_id"], tenant_id=env["tid"], role="admin")
    r = await http_client.post("/api/admin/onboarding/advance", headers=h, json={
        "current_step": "step_1_welcome",
        "step_data": {},
    })
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["current_step"] == "step_2_tenant_info"
    assert "step_1_welcome" in body["steps_completed"]
    # Avanzo paso 2 con datos
    r2 = await http_client.post("/api/admin/onboarding/advance", headers=h, json={
        "current_step": "step_2_tenant_info",
        "step_data": {"rfc": "ABCD050101AAA", "phone": "+525512345678"},
    })
    assert r2.json()["data"]["current_step"] == "step_3_project_client"
    # Verificar persistencia via state
    rs = await http_client.get("/api/admin/onboarding/state", headers=h)
    sd = rs.json()["data"]["step_data"]
    assert sd["step_2_tenant_info"]["rfc"] == "ABCD050101AAA"


@pytest.mark.asyncio
async def test_skip_mandatory_step_rejected_422(env, http_client):
    h = _bearer(user_id=env["user_id"], tenant_id=env["tid"], role="admin")
    # welcome es mandatorio → no se puede saltar
    r = await http_client.post("/api/admin/onboarding/skip-step", headers=h, json={
        "current_step": "step_1_welcome",
    })
    assert r.status_code == 422
    # catalog también es mandatorio
    r2 = await http_client.post("/api/admin/onboarding/skip-step", headers=h, json={
        "current_step": "step_5_catalog",
    })
    assert r2.status_code == 422


@pytest.mark.asyncio
async def test_skip_optional_step_moves_forward(env, http_client):
    h = _bearer(user_id=env["user_id"], tenant_id=env["tid"], role="admin")
    # Saltar paso 4 (carriers) — opcional
    r = await http_client.post("/api/admin/onboarding/skip-step", headers=h, json={
        "current_step": "step_4_carriers",
    })
    assert r.status_code == 200
    assert r.json()["data"]["current_step"] == "step_5_catalog"


@pytest.mark.asyncio
async def test_complete_idempotent(env, http_client):
    h = _bearer(user_id=env["user_id"], tenant_id=env["tid"], role="admin")
    r1 = await http_client.post("/api/admin/onboarding/complete", headers=h)
    assert r1.status_code == 200
    first_completed = r1.json()["data"]["completed_at"]
    assert first_completed is not None
    # 2do POST no rompe
    r2 = await http_client.post("/api/admin/onboarding/complete", headers=h)
    assert r2.status_code == 200
    # Y should_auto_open ahora es false
    state = await http_client.get("/api/admin/onboarding/state", headers=h)
    assert state.json()["data"]["should_auto_open"] is False
    assert state.json()["data"]["is_completed"] is True


# ──────────────────────────────────────────────────────────────────────
# Catálogo MX estándar
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_seed_mx_catalog_inserts_and_is_idempotent(env, http_client):
    h = _bearer(user_id=env["user_id"], tenant_id=env["tid"], role="admin")
    r1 = await http_client.post("/api/admin/onboarding/seed-mx-catalog", headers=h)
    assert r1.status_code == 200
    body = r1.json()["data"]
    assert body["motivos_inserted"] == 12
    # Cada solución mapea a >=1 motivo, hay 18 soluciones con motivo_codes varios
    assert body["soluciones_inserted"] > 18  # algunas mapean a múltiples motivos

    # 2da llamada → todo skipped
    r2 = await http_client.post("/api/admin/onboarding/seed-mx-catalog", headers=h)
    body2 = r2.json()["data"]
    assert body2["motivos_inserted"] == 0
    assert body2["motivos_skipped"] == 12
    assert body2["soluciones_inserted"] == 0

    # Verificar conteo real en la BD
    db = env["db"]
    n_motivos = await db.motivos.count_documents({"tenant_id": env["tid"]})
    assert n_motivos == 12


# ──────────────────────────────────────────────────────────────────────
# 2do admin del tenant — pre_completed_by_tenant
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pre_completed_detects_existing_state(env, http_client):
    """2do admin entra a un tenant que ya tiene cliente + catálogo cargado."""
    db = env["db"]
    tid = env["tid"]
    # Sembrar estado "como si el 1er admin lo dejara"
    await db.tenants.update_one(
        {"id": tid},
        {"$set": {"rfc": "TENT050101AAA", "phone": "+525511112222"}},
    )
    await db.clients.insert_one({
        "id": new_id(), "tenant_id": tid, "project_id": new_id(),
        "name": "Cliente seed", "ingest_mode": "webhook",
    })
    # Inyectar 1 motivo + 1 solución
    mid = new_id()
    await db.motivos.insert_one({
        "id": mid, "tenant_id": tid, "code": "X", "name": "X",
        "restricted": False, "active": True,
    })
    await db.soluciones.insert_one({
        "id": new_id(), "tenant_id": tid, "motivo_id": mid, "name": "S",
        "steps": [], "automatable": False,
    })

    # 2do admin (rol superadmin)
    admin2 = new_id()
    await db.users.insert_one({
        "id": admin2, "tenant_id": tid, "email": "admin2@t",
        "role": "superadmin", "status": "active",
    })
    h = _bearer(user_id=admin2, tenant_id=tid, role="superadmin")
    r = await http_client.get("/api/admin/onboarding/state", headers=h)
    body = r.json()["data"]
    assert "step_2_tenant_info" in body["pre_completed_by_tenant"]
    assert "step_3_project_client" in body["pre_completed_by_tenant"]
    assert "step_5_catalog" in body["pre_completed_by_tenant"]
    # 2do admin sigue debiendo ver welcome (informativo)
    assert "step_1_welcome" not in body["pre_completed_by_tenant"]


@pytest.mark.asyncio
async def test_advance_skips_pre_completed_steps(env, http_client):
    """Si user completa welcome y los siguientes ya están en steps_completed,
    el `next_step` salta al primero realmente pendiente."""
    h = _bearer(user_id=env["user_id"], tenant_id=env["tid"], role="admin")
    # Pre-marcar step_2 y step_3 como completados (simulando pre_completed_by_tenant
    # aplicado al doc via /advance silenciosos del frontend para el 2do admin).
    for s in ("step_2_tenant_info", "step_3_project_client"):
        await http_client.post("/api/admin/onboarding/advance", headers=h, json={
            "current_step": s, "step_data": {},
        })
    # Ahora completar welcome
    r = await http_client.post("/api/admin/onboarding/advance", headers=h, json={
        "current_step": "step_1_welcome", "step_data": {},
    })
    body = r.json()["data"]
    # Como ya están completados step_2 y step_3, debe avanzar a step_4
    assert body["current_step"] == "step_4_carriers"


# ──────────────────────────────────────────────────────────────────────
# RBAC
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_state_requires_admin(env, http_client):
    db = env["db"]
    sup_id = new_id()
    await db.users.insert_one({
        "id": sup_id, "tenant_id": env["tid"], "email": "sup@t",
        "role": "supervisor", "status": "active",
    })
    h = _bearer(user_id=sup_id, tenant_id=env["tid"], role="supervisor")
    r = await http_client.get("/api/admin/onboarding/state", headers=h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_models_mandatory_steps():
    """Sanity check: welcome y catalog están en MANDATORY_STEPS."""
    from models.onboarding import (
        MANDATORY_STEPS,
        STEP_CATALOG,
        STEP_WELCOME,
        STEP_ORDER,
    )
    assert STEP_WELCOME in MANDATORY_STEPS
    assert STEP_CATALOG in MANDATORY_STEPS
    assert len(STEP_ORDER) == 6
