"""Iter65 · Proxy autenticado para imágenes de Routal.

Las URLs ``https://api.routal.com/v3/stop/report/...`` requieren
``?private_key=`` para acceder. El proxy backend:
  - Valida que el ticket pertenezca al tenant.
  - Valida que el image_id esté en el report guardado (anti-IDOR).
  - No expone el api_key al frontend.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id


def _bearer(*, user_id, tenant_id, role="agent", email="u@t.io"):
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
    user_id = new_id()
    client_id = new_id()
    guia_id = new_id()
    ticket_id = new_id()

    await db.tenants.insert_one(
        {"id": t_id, "slug": "t-65", "name": "T-65", "status": "active"})
    await db.users.insert_one({
        "id": user_id, "tenant_id": t_id, "email": "ag@t-65.io",
        "role": "agent", "password_hash": "x", "status": "active",
    })
    await db.clients.insert_one({
        "id": client_id, "tenant_id": t_id, "name": "Cli T65",
        "slug": "cli-t65", "status": "active",
    })
    await db.guias.insert_one({
        "id": guia_id, "tenant_id": t_id, "client_id": client_id,
        "tracking_id": "TRK-65", "carrier_code": "routal",
        "carrier_meta": {"routal_report": {
            "report_id": "rep-1",
            "images": [
                {"id": "img-A", "url": "https://api.routal.com/x"},
                {"id": "img-B", "url": "https://api.routal.com/y"},
            ],
        }},
    })
    await db.tickets.insert_one({
        "id": ticket_id, "tenant_id": t_id, "client_id": client_id,
        "guia_id": guia_id, "status": "pending",
        "carrier_incident_detail": {
            "report_id": "rep-1",
            "images": [{"id": "img-A", "url": "..."},
                       {"id": "img-B", "url": "..."}],
        },
    })
    return {"tenant_id": t_id, "user_id": user_id,
            "ticket_id": ticket_id, "guia_id": guia_id}


@pytest.mark.asyncio
async def test_proxy_rejects_image_id_not_in_ticket(http_client, env):
    h = _bearer(user_id=env["user_id"], tenant_id=env["tenant_id"])
    r = await http_client.get(
        "/api/agent/routal/image-proxy",
        params={"ticket_id": env["ticket_id"], "report_id": "rep-1",
                "image_id": "img-Z-NOT-IN-TICKET"},
        headers=h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_proxy_rejects_ticket_from_other_tenant(http_client, env, db):
    # Crear otro tenant + ticket
    t2 = new_id(); u2 = new_id()
    await db.tenants.insert_one(
        {"id": t2, "slug": "t-65b", "name": "T-65b", "status": "active"})
    await db.users.insert_one({
        "id": u2, "tenant_id": t2, "email": "x@t-65b.io",
        "role": "agent", "password_hash": "x", "status": "active",
    })
    h = _bearer(user_id=u2, tenant_id=t2)
    # Tratamos de leer ticket del otro tenant → 404 (no leak)
    r = await http_client.get(
        "/api/agent/routal/image-proxy",
        params={"ticket_id": env["ticket_id"], "report_id": "rep-1",
                "image_id": "img-A"},
        headers=h)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_proxy_unauthenticated_denied(http_client, env):
    r = await http_client.get(
        "/api/agent/routal/image-proxy",
        params={"ticket_id": env["ticket_id"], "report_id": "rep-1",
                "image_id": "img-A"})
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_proxy_returns_503_when_no_api_key(http_client, env):
    """ticket existe + image_id válido pero el cliente no tiene
    api_key_ref configurado → 503 (no expone el error de credenciales
    como 500 ni 401 al frontend)."""
    h = _bearer(user_id=env["user_id"], tenant_id=env["tenant_id"])
    r = await http_client.get(
        "/api/agent/routal/image-proxy",
        params={"ticket_id": env["ticket_id"], "report_id": "rep-1",
                "image_id": "img-A"},
        headers=h)
    assert r.status_code == 503
