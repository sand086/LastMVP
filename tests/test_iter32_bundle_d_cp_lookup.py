"""Iter32 — Bundle D mejora · CP lookup endpoint con cache."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id
import routes.util_cp as cp_mod


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
    await db.tenants.insert_one(
        {"id": tid, "slug": "t1", "name": "T1", "status": "active"},
    )
    await db.users.insert_one(
        {"id": user_id, "tenant_id": tid, "email": "a@t",
         "role": "admin", "status": "active"},
    )
    # Limpiar rate limit state global
    cp_mod._rate_limit.clear()
    return {"tid": tid, "user_id": user_id, "db": db}


@pytest.mark.asyncio
async def test_cp_lookup_invalid_format_422(env, http_client):
    h = _bearer(user_id=env["user_id"], tenant_id=env["tid"])
    r = await http_client.get("/api/util/cp-lookup/ABCDE", headers=h)
    # FastAPI Path validator → 422
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_cp_lookup_uses_cache(env, http_client, monkeypatch):
    """Si el cache tiene valor fresco, NO se debe llamar a la API externa."""
    db = env["db"]
    # Sembramos cache para 06700
    now = datetime.now(timezone.utc)
    await db.cp_lookup_cache.insert_one({
        "id": "cache-1", "cp": "06700",
        "data": {"cp": "06700", "estado": "Ciudad de México",
                 "ciudad": "Ciudad de México",
                 "colonias": [{"colonia": "Roma Norte",
                               "estado": "Ciudad de México",
                               "ciudad": "Ciudad de México"}]},
        "fetched_at": now.isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(),
    })

    # Mock _fetch_zippopotam para que falle si se llama
    called = {"count": 0}

    async def _should_not_be_called(cp):
        called["count"] += 1
        return None

    monkeypatch.setattr(cp_mod, "_fetch_zippopotam", _should_not_be_called)

    h = _bearer(user_id=env["user_id"], tenant_id=env["tid"])
    r = await http_client.get("/api/util/cp-lookup/06700", headers=h)
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["source"] == "cache"
    assert body["data"]["estado"] == "Ciudad de México"
    assert called["count"] == 0


@pytest.mark.asyncio
async def test_cp_lookup_fetches_and_caches(env, http_client, monkeypatch):
    """Sin cache, debe llamar externo y persistir resultado."""
    await env["db"].cp_lookup_cache.delete_many({"cp": "11000"})

    async def _fake_fetch(cp):
        assert cp == "11000"
        return {
            "cp": cp, "estado": "Ciudad de México",
            "ciudad": "Ciudad de México",
            "colonias": [{"colonia": "Polanco", "estado": "Ciudad de México",
                          "ciudad": "Ciudad de México"}],
        }

    monkeypatch.setattr(cp_mod, "_fetch_zippopotam", _fake_fetch)
    h = _bearer(user_id=env["user_id"], tenant_id=env["tid"])
    r = await http_client.get("/api/util/cp-lookup/11000", headers=h)
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["source"] == "zippopotam"
    assert body["data"]["colonias"][0]["colonia"] == "Polanco"
    # Verificar persistencia
    cached = await env["db"].cp_lookup_cache.find_one({"cp": "11000"}, {"_id": 0})
    assert cached is not None
    assert "expires_at" in cached


@pytest.mark.asyncio
async def test_cp_lookup_not_found_404(env, http_client, monkeypatch):
    await env["db"].cp_lookup_cache.delete_many({"cp": "99999"})

    async def _fake_fetch(cp):
        return None

    monkeypatch.setattr(cp_mod, "_fetch_zippopotam", _fake_fetch)
    h = _bearer(user_id=env["user_id"], tenant_id=env["tid"])
    r = await http_client.get("/api/util/cp-lookup/99999", headers=h)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_cp_lookup_rate_limit_429(env, http_client, monkeypatch):
    """Después de 30 lookups en menos de 60s, devolver 429."""
    async def _fake_fetch(cp):
        return {"cp": cp, "estado": "CDMX", "ciudad": "CDMX", "colonias": []}

    monkeypatch.setattr(cp_mod, "_fetch_zippopotam", _fake_fetch)
    h = _bearer(user_id=env["user_id"], tenant_id=env["tid"])
    # 30 OK
    for i in range(30):
        cp = f"{10000 + i}"
        r = await http_client.get(f"/api/util/cp-lookup/{cp}", headers=h)
        assert r.status_code == 200, f"lookup {i} fallo: {r.text}"
    # 31 → 429
    r = await http_client.get("/api/util/cp-lookup/12345", headers=h)
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_cp_lookup_stale_cache_fallback(env, http_client, monkeypatch):
    """Si zippopotam falla pero hay cache stale, devolver stale_cache."""
    db = env["db"]
    now = datetime.now(timezone.utc)
    # Seed con expires_at en el pasado (cache stale)
    await db.cp_lookup_cache.insert_one({
        "id": "stale-1", "cp": "44100",
        "data": {"cp": "44100", "estado": "Jalisco", "ciudad": "Guadalajara",
                 "colonias": []},
        "fetched_at": (now - timedelta(days=120)).isoformat(),
        "expires_at": (now - timedelta(days=60)).isoformat(),
    })

    async def _failing_fetch(cp):
        return None

    monkeypatch.setattr(cp_mod, "_fetch_zippopotam", _failing_fetch)
    h = _bearer(user_id=env["user_id"], tenant_id=env["tid"])
    r = await http_client.get("/api/util/cp-lookup/44100", headers=h)
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["source"] == "stale_cache"
    assert body["data"]["estado"] == "Jalisco"


@pytest.mark.asyncio
async def test_client_create_accepts_address_mx(env, http_client):
    """ClientCreate model accepts address_mx field (Bundle D)."""
    from models.admin import ClientCreate, MxAddress
    # Validar que el modelo Pydantic acepta MxAddress
    payload = {
        "project_id": "a" * 36, "name": "Cubbo",
        "address_mx": {
            "calle": "Av. Insurgentes", "numero_exterior": "1234",
            "colonia": "Roma Norte", "codigo_postal": "06700",
            "ciudad": "Ciudad de México", "estado": "CDMX",
            "country": "MX",
        },
    }
    m = ClientCreate(**payload)
    assert isinstance(m.address_mx, MxAddress)
    assert m.address_mx.codigo_postal == "06700"
    assert m.address_mx.country == "MX"


def test_address_mx_rejects_invalid_cp():
    """CP inválido (no 5 dígitos) debe fallar la validación Pydantic."""
    from pydantic import ValidationError
    from models.admin import MxAddress
    with pytest.raises(ValidationError):
        MxAddress(codigo_postal="ABC")
    with pytest.raises(ValidationError):
        MxAddress(codigo_postal="123")
