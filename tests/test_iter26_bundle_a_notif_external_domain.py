"""Iter26 — Bundle A · FIX-A3 — Test send con warning de dominio externo.

Cubre:
  * Dominio en whitelist global → no warning, envía OK.
  * Dominio externo sin confirmed_external → 422 con extra error
    EXTERNAL_DOMAIN_REQUIRES_CONFIRMATION.
  * Dominio externo con confirmed_external=True → crea audit event y envía.
  * CRUD de tenant_test_domains (GET + POST + DELETE).
  * Whitelist por tenant: dominio agregado por tenant NO afecta a otro tenant.
"""
from __future__ import annotations
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
    tid_a, tid_b = new_id(), new_id()
    admin_a, admin_b = new_id(), new_id()
    await db.tenants.insert_many([
        {"id": tid_a, "slug": "ta", "name": "TA", "status": "active"},
        {"id": tid_b, "slug": "tb", "name": "TB", "status": "active"},
    ])
    await db.users.insert_many([
        {"id": admin_a, "tenant_id": tid_a, "email": "admin@my-mensajeria.com",
         "role": "admin", "status": "active", "name": "AA"},
        {"id": admin_b, "tenant_id": tid_b, "email": "admin@thinkme.com.mx",
         "role": "admin", "status": "active", "name": "BB"},
    ])
    return {"tid_a": tid_a, "tid_b": tid_b,
            "admin_a": admin_a, "admin_b": admin_b, "db": db}


@pytest.mark.asyncio
async def test_test_send_whitelist_domain_no_warning(env, http_client, monkeypatch):
    """Dominio en whitelist global → enviar OK sin warning."""
    # Mock send_email en el módulo donde se importa (routes.admin_notifications)
    import routes.admin_notifications as an

    class _OkResult:
        ok = True

        def to_dict(self):  # noqa: D401
            return {"ok": True, "provider_id": "fake-id"}

    async def _fake_send(**kwargs):  # noqa: ANN001
        return _OkResult()

    monkeypatch.setattr(an, "send_email", _fake_send)
    h = _bearer(user_id=env["admin_a"], tenant_id=env["tid_a"])
    r = await http_client.post(
        "/api/admin/notifications/test",
        json={"to": "qa@my-mensajeria.com", "confirmed_external": False},
        headers=h,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["external_domain"] is False
    assert data["audit_event_id"] is None


@pytest.mark.asyncio
async def test_test_send_external_domain_requires_confirmation(env, http_client):
    h = _bearer(user_id=env["admin_a"], tenant_id=env["tid_a"])
    r = await http_client.post(
        "/api/admin/notifications/test",
        json={"to": "cliente@cubbo.com"},
        headers=h,
    )
    assert r.status_code == 422, r.text
    body = r.json()
    # Debe haber un extra error con code EXTERNAL_DOMAIN_REQUIRES_CONFIRMATION
    codes = [e["code"] for e in body["errors"]]
    assert "EXTERNAL_DOMAIN_REQUIRES_CONFIRMATION" in codes


@pytest.mark.asyncio
async def test_test_send_external_with_confirmed_creates_audit(env, http_client, monkeypatch):
    import routes.admin_notifications as an

    class _OkResult:
        ok = True

        def to_dict(self):
            return {"ok": True, "provider_id": "fake"}

    async def _fake_send(**kwargs):
        return _OkResult()

    monkeypatch.setattr(an, "send_email", _fake_send)
    h = _bearer(user_id=env["admin_a"], tenant_id=env["tid_a"])
    r = await http_client.post(
        "/api/admin/notifications/test",
        json={"to": "cliente@cubbo.com", "confirmed_external": True},
        headers=h,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["external_domain"] is True
    assert data["audit_event_id"]
    # Verificar persistencia del audit
    audit = await env["db"].user_audit_log.find_one(
        {"id": data["audit_event_id"]}, {"_id": 0},
    )
    assert audit is not None
    assert audit["action"] == "notif.test_external"
    assert audit["tenant_id"] == env["tid_a"]
    assert audit["target_email"] == "cliente@cubbo.com"


@pytest.mark.asyncio
async def test_tenant_test_domains_crud(env, http_client):
    h = _bearer(user_id=env["admin_a"], tenant_id=env["tid_a"])
    # GET inicial → solo globals
    r = await http_client.get("/api/admin/test-domains", headers=h)
    assert r.status_code == 200
    data = r.json()["data"]
    assert "my-mensajeria.com" in data["global_domains"]
    assert data["tenant_domains"] == []

    # POST agregar
    r2 = await http_client.post(
        "/api/admin/test-domains",
        json={"domain": "Socio-Comercial.com"},
        headers=h,
    )
    assert r2.status_code == 200, r2.text
    new_domain = r2.json()["data"]["domain"]
    assert new_domain["domain"] == "socio-comercial.com"  # normalizado

    # GET después → debe aparecer
    r3 = await http_client.get("/api/admin/test-domains", headers=h)
    assert r3.status_code == 200
    domains = [d["domain"] for d in r3.json()["data"]["tenant_domains"]]
    assert "socio-comercial.com" in domains

    # DELETE
    r4 = await http_client.delete(
        f"/api/admin/test-domains/{new_domain['id']}", headers=h,
    )
    assert r4.status_code == 200
    assert r4.json()["data"]["deleted"] is True

    # GET final → vacío
    r5 = await http_client.get("/api/admin/test-domains", headers=h)
    assert r5.json()["data"]["tenant_domains"] == []


@pytest.mark.asyncio
async def test_tenant_domain_isolation(env, http_client, monkeypatch):
    """Dominio agregado por tenant A NO debe estar whitelisted para tenant B."""
    import routes.admin_notifications as an

    class _OkResult:
        ok = True

        def to_dict(self):
            return {"ok": True}

    async def _fake_send(**kwargs):
        return _OkResult()

    monkeypatch.setattr(an, "send_email", _fake_send)

    # Tenant A agrega socio-comercial.com a su whitelist
    h_a = _bearer(user_id=env["admin_a"], tenant_id=env["tid_a"])
    await http_client.post(
        "/api/admin/test-domains",
        json={"domain": "socio-comercial.com"}, headers=h_a,
    )
    # Tenant A puede enviar sin warning
    r_a = await http_client.post(
        "/api/admin/notifications/test",
        json={"to": "qa@socio-comercial.com"}, headers=h_a,
    )
    assert r_a.status_code == 200
    assert r_a.json()["data"]["external_domain"] is False

    # Tenant B intenta enviar al mismo dominio → SÍ external
    h_b = _bearer(user_id=env["admin_b"], tenant_id=env["tid_b"])
    r_b = await http_client.post(
        "/api/admin/notifications/test",
        json={"to": "qa@socio-comercial.com"}, headers=h_b,
    )
    assert r_b.status_code == 422


@pytest.mark.asyncio
async def test_global_domain_cannot_be_added_again(env, http_client):
    h = _bearer(user_id=env["admin_a"], tenant_id=env["tid_a"])
    r = await http_client.post(
        "/api/admin/test-domains",
        json={"domain": "my-mensajeria.com"}, headers=h,
    )
    assert r.status_code == 422
