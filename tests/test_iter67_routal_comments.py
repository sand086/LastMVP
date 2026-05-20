"""Iter67 · Comentarios bidireccionales con Routal.

Cubre el endpoint backend ``/api/agent/routal/comments``:
  - GET requiere ticket Routal con stop_id
  - POST valida tenant/IDOR
  - POST en modo append agrega header con timestamp + autor
  - Historial se guarda con audit completo (incluso si Routal falla)
  - Rol < agent → 403
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from server import app
from core.security import create_access_token
from core.uuid import new_id


def _bearer(*, user_id, tenant_id, role="agent", email="ag@t.io"):
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
        {"id": t_id, "slug": "t-67", "name": "T-67", "status": "active"})
    await db.users.insert_one({
        "id": user_id, "tenant_id": t_id, "email": "ag@t-67.io",
        "role": "agent", "password_hash": "x", "status": "active",
    })
    await db.clients.insert_one({
        "id": client_id, "tenant_id": t_id, "name": "Cli T67",
        "slug": "cli-t67", "status": "active",
        "carriers": {"routal": {"api_key_ref": "FAKE_REF",
                                 "project_ids": ["p1"]}},
    })
    await db.guias.insert_one({
        "id": guia_id, "tenant_id": t_id, "client_id": client_id,
        "tracking_id": "TRK-67", "carrier_code": "routal",
        "raw_payload": {"stop_id": "stop-1", "plan_id": "plan-1"},
        "carrier_meta": {},
    })
    await db.tickets.insert_one({
        "id": ticket_id, "tenant_id": t_id, "client_id": client_id,
        "guia_id": guia_id, "status": "pending",
    })
    return {"tenant_id": t_id, "user_id": user_id,
            "ticket_id": ticket_id, "guia_id": guia_id}


# Helper para mockear decrypt (lo importan dentro de _resolve_routal_api_key)
def _mock_api_key():
    return patch("core.crypto.decrypt",
                 return_value="FAKE_API_KEY_XXXXXXXXXXXXXXXX")


@pytest.mark.asyncio
async def test_post_comment_append_with_header(http_client, db, env):
    with _mock_api_key(), \
         patch("routes.agent_routal_comments.httpx.AsyncClient") as mock_cli:
        # Mock GET de plan/stops (para previo) y PUT de stop
        inst = mock_cli.return_value.__aenter__.return_value
        inst.get = AsyncMock(return_value=type("R", (), {
            "status_code": 200,
            "json": lambda self: [{"id": "stop-1", "comments": ""}],
        })())
        inst.put = AsyncMock(return_value=type("R", (), {
            "status_code": 200, "text": "ok",
            "json": lambda self: {"id": "stop-1"},
        })())
        h = _bearer(user_id=env["user_id"], tenant_id=env["tenant_id"])
        r = await http_client.post(
            "/api/agent/routal/comments", headers=h,
            json={"ticket_id": env["ticket_id"],
                  "comment": "Llamar al portero", "mode": "append"})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert "[" in d["current_comment"]  # header timestamped
        assert "@ag" in d["current_comment"]  # agent email username
        assert "Llamar al portero" in d["current_comment"]
        assert d["mode"] == "append"

    # Audit log persistido en guia
    g = await db.guias.find_one({"id": env["guia_id"]}, {"_id": 0})
    hist = g["carrier_meta"]["routal_comments_history"]
    assert len(hist) == 1
    assert hist[0]["comment"] == "Llamar al portero"
    assert hist[0]["success"] is True
    assert hist[0]["agent_email"] == "ag@t-67.io"


@pytest.mark.asyncio
async def test_post_comment_append_preserves_previous(http_client, db, env):
    with _mock_api_key(), \
         patch("routes.agent_routal_comments.httpx.AsyncClient") as mock_cli:
        inst = mock_cli.return_value.__aenter__.return_value
        # Routal ya tiene comentario previo
        inst.get = AsyncMock(return_value=type("R", (), {
            "status_code": 200,
            "json": lambda self: [
                {"id": "stop-1", "comments": "[01/01 · @prev]\nViejo"},
            ],
        })())
        inst.put = AsyncMock(return_value=type("R", (), {
            "status_code": 200, "text": "ok",
            "json": lambda self: {"id": "stop-1"},
        })())
        h = _bearer(user_id=env["user_id"], tenant_id=env["tenant_id"])
        r = await http_client.post(
            "/api/agent/routal/comments", headers=h,
            json={"ticket_id": env["ticket_id"],
                  "comment": "Nueva info", "mode": "append"})
        d = r.json()["data"]
        assert "Nueva info" in d["current_comment"]
        assert "---" in d["current_comment"]
        assert "Viejo" in d["current_comment"]  # previo preservado


@pytest.mark.asyncio
async def test_post_comment_replace_overwrites(http_client, env):
    with _mock_api_key(), \
         patch("routes.agent_routal_comments.httpx.AsyncClient") as mock_cli:
        inst = mock_cli.return_value.__aenter__.return_value
        inst.put = AsyncMock(return_value=type("R", (), {
            "status_code": 200, "text": "ok",
            "json": lambda self: {"id": "stop-1"},
        })())
        h = _bearer(user_id=env["user_id"], tenant_id=env["tenant_id"])
        r = await http_client.post(
            "/api/agent/routal/comments", headers=h,
            json={"ticket_id": env["ticket_id"],
                  "comment": "TOTAL REPLACE", "mode": "replace"})
        d = r.json()["data"]
        # No header en modo replace
        assert d["current_comment"] == "TOTAL REPLACE"


@pytest.mark.asyncio
async def test_get_comments_ok(http_client, env):
    with _mock_api_key(), \
         patch("routes.agent_routal_comments.httpx.AsyncClient") as mock_cli:
        inst = mock_cli.return_value.__aenter__.return_value
        inst.get = AsyncMock(return_value=type("R", (), {
            "status_code": 200,
            "json": lambda self: [{"id": "stop-1", "comments": "Hola"}],
        })())
        h = _bearer(user_id=env["user_id"], tenant_id=env["tenant_id"])
        r = await http_client.get(
            "/api/agent/routal/comments",
            params={"ticket_id": env["ticket_id"]}, headers=h)
        assert r.status_code == 200
        assert r.json()["data"]["current_comment"] == "Hola"


@pytest.mark.asyncio
async def test_cross_tenant_denied(http_client, env, db):
    t2 = new_id(); u2 = new_id()
    await db.tenants.insert_one(
        {"id": t2, "slug": "t-67b", "name": "T-67b", "status": "active"})
    await db.users.insert_one({
        "id": u2, "tenant_id": t2, "email": "x@t-67b.io",
        "role": "agent", "password_hash": "x", "status": "active"})
    h = _bearer(user_id=u2, tenant_id=t2)
    r = await http_client.get(
        "/api/agent/routal/comments",
        params={"ticket_id": env["ticket_id"]}, headers=h)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_non_routal_guia_rejected(http_client, db, env):
    # Cambiamos carrier_code a fedex
    await db.guias.update_one({"id": env["guia_id"]},
                              {"$set": {"carrier_code": "fedex"}})
    h = _bearer(user_id=env["user_id"], tenant_id=env["tenant_id"])
    r = await http_client.get(
        "/api/agent/routal/comments",
        params={"ticket_id": env["ticket_id"]}, headers=h)
    assert r.status_code == 400
    assert "Routal" in r.json()["detail"]


@pytest.mark.asyncio
async def test_role_below_agent_denied(http_client, db, env):
    # Crear un client_viewer real en DB (el middleware lee role del DB)
    viewer_id = new_id()
    await db.users.insert_one({
        "id": viewer_id, "tenant_id": env["tenant_id"],
        "email": "viewer@t-67.io", "role": "client_viewer",
        "password_hash": "x", "status": "active"})
    h = _bearer(user_id=viewer_id, tenant_id=env["tenant_id"],
                role="client_viewer", email="viewer@t-67.io")
    r = await http_client.post(
        "/api/agent/routal/comments", headers=h,
        json={"ticket_id": env["ticket_id"], "comment": "x",
              "mode": "append"})
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_routal_failure_persists_audit(http_client, db, env):
    """Si Routal devuelve 500, NO debemos perder el intento — debe quedar
    en el historial con success=False para diagnóstico."""
    with _mock_api_key(), \
         patch("routes.agent_routal_comments.httpx.AsyncClient") as mock_cli:
        inst = mock_cli.return_value.__aenter__.return_value
        inst.get = AsyncMock(return_value=type("R", (), {
            "status_code": 200, "json": lambda self: [],
        })())
        inst.put = AsyncMock(return_value=type("R", (), {
            "status_code": 500, "text": "Routal down",
            "json": lambda self: {},
        })())
        h = _bearer(user_id=env["user_id"], tenant_id=env["tenant_id"])
        r = await http_client.post(
            "/api/agent/routal/comments", headers=h,
            json={"ticket_id": env["ticket_id"],
                  "comment": "Test fail", "mode": "append"})
        assert r.status_code == 502

    g = await db.guias.find_one({"id": env["guia_id"]}, {"_id": 0})
    hist = g["carrier_meta"]["routal_comments_history"]
    assert len(hist) == 1
    assert hist[0]["success"] is False
    assert "500" in (hist[0]["error"] or "")
