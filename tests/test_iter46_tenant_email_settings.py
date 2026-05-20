"""Iter46 · TenantEmailSettings — credenciales Resend por tenant.

Cubre:
  GET   /api/admin/email-settings
  PUT   /api/admin/email-settings  (upsert con/sin api_key)
  POST  /api/admin/email-settings/test
  DELETE /api/admin/email-settings
  - aislamiento por tenant (T_A no ve config de T_B)
  - resolve_credentials() devuelve env si no hay config tenant
  - api_key encriptada, NUNCA expuesta en respuestas
  - send_email(tenant_id=...) usa la config del tenant
"""
from __future__ import annotations
from datetime import datetime, timezone
import os
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token, hash_password
from core.uuid import new_id


def _bearer(*, user_id: str, tenant_id: str, role: str = "admin",
            email: str = "admin@t.io"):
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
    """2 tenants para validar aislamiento."""
    ta = new_id()
    tb = new_id()
    admin_a = new_id()
    admin_b = new_id()
    agent_a = new_id()
    pwd = hash_password("x")
    await db.tenants.insert_many([
        {"id": ta, "slug": "t-a", "name": "T-A", "status": "active"},
        {"id": tb, "slug": "t-b", "name": "T-B", "status": "active"},
    ])
    await db.users.insert_many([
        {"id": admin_a, "tenant_id": ta, "email": "admin-a@t.io",
         "role": "admin", "status": "active", "password_hash": pwd},
        {"id": admin_b, "tenant_id": tb, "email": "admin-b@t.io",
         "role": "admin", "status": "active", "password_hash": pwd},
        {"id": agent_a, "tenant_id": ta, "email": "agent-a@t.io",
         "role": "agent", "status": "active", "password_hash": pwd},
    ])
    return {"ta": ta, "tb": tb, "admin_a": admin_a, "admin_b": admin_b,
            "agent_a": agent_a}


# ────────────────────────────────────────────────────────────────────────
class TestGet:
    async def test_unconfigured_returns_disabled_view(self, env, http_client):
        h = _bearer(user_id=env["admin_a"], tenant_id=env["ta"])
        r = await http_client.get("/api/admin/email-settings", headers=h)
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["configured"] is False
        assert d["status"] == "disabled"
        assert d["api_key_hint"] == ""

    async def test_agent_forbidden(self, env, http_client):
        h = _bearer(user_id=env["agent_a"], tenant_id=env["ta"], role="agent")
        r = await http_client.get("/api/admin/email-settings", headers=h)
        assert r.status_code == 403


# ────────────────────────────────────────────────────────────────────────
class TestUpsert:
    async def test_creates_with_api_key(self, env, http_client):
        h = _bearer(user_id=env["admin_a"], tenant_id=env["ta"])
        r = await http_client.put("/api/admin/email-settings", headers=h, json={
            "sender_email": "soporte@miempresa.com",
            "sender_name": "Mi Empresa",
            "api_key": "re_test_abcdef1234567890",
            "reply_to_default": "hola@miempresa.com",
            "status": "active",
        })
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["configured"] is True
        assert d["status"] == "active"
        assert d["api_key_hint"] == "****7890"
        assert d["sender_email"] == "soporte@miempresa.com"

    async def test_api_key_encrypted_in_db(self, env, http_client, db):
        h = _bearer(user_id=env["admin_a"], tenant_id=env["ta"])
        await http_client.put("/api/admin/email-settings", headers=h, json={
            "sender_email": "x@y.com", "sender_name": "X",
            "api_key": "re_supersecret_key_xyz",
            "status": "active",
        })
        doc = await db.tenant_email_settings.find_one(
            {"tenant_id": env["ta"]}, {"_id": 0})
        # plaintext debe NO aparecer en BD
        assert "re_supersecret_key_xyz" not in str(doc)
        assert doc["api_key_ref"] != "re_supersecret_key_xyz"
        assert doc["api_key_last4"] == "_xyz"

    async def test_update_preserves_api_key_when_omitted(self, env, http_client):
        h = _bearer(user_id=env["admin_a"], tenant_id=env["ta"])
        # 1) Crear con key
        await http_client.put("/api/admin/email-settings", headers=h, json={
            "sender_email": "x@y.com", "sender_name": "X",
            "api_key": "re_first_key_aaaa", "status": "active",
        })
        # 2) Actualizar SIN api_key → debe preservarse
        r = await http_client.put("/api/admin/email-settings", headers=h, json={
            "sender_email": "z@y.com", "sender_name": "Z",
            "status": "active",
        })
        d = r.json()["data"]
        assert d["api_key_hint"] == "****aaaa"  # se preservó
        assert d["sender_email"] == "z@y.com"

    async def test_invalid_email_rejected(self, env, http_client):
        h = _bearer(user_id=env["admin_a"], tenant_id=env["ta"])
        r = await http_client.put("/api/admin/email-settings", headers=h, json={
            "sender_email": "no-es-email", "sender_name": "X",
            "status": "active",
        })
        assert r.status_code == 422


# ────────────────────────────────────────────────────────────────────────
class TestTenantIsolation:
    async def test_tenant_a_cannot_see_b(self, env, http_client, db):
        # Sembrar config en T-B
        await db.tenant_email_settings.insert_one({
            "tenant_id": env["tb"], "sender_email": "secreto-b@b.com",
            "sender_name": "Tenant B", "status": "active",
            "api_key_ref": "encrypted_xxxx", "api_key_last4": "9999",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        # Admin A consulta su propia config: debe estar VACÍA
        h_a = _bearer(user_id=env["admin_a"], tenant_id=env["ta"])
        r_a = await http_client.get("/api/admin/email-settings", headers=h_a)
        d_a = r_a.json()["data"]
        assert d_a["configured"] is False
        assert d_a["sender_email"] == ""
        # Admin B consulta SU config: ve la suya
        h_b = _bearer(user_id=env["admin_b"], tenant_id=env["tb"],
                      email="admin-b@t.io")
        r_b = await http_client.get("/api/admin/email-settings", headers=h_b)
        d_b = r_b.json()["data"]
        assert d_b["sender_email"] == "secreto-b@b.com"
        assert d_b["api_key_hint"] == "****9999"


# ────────────────────────────────────────────────────────────────────────
class TestDisable:
    async def test_disable_sets_status(self, env, http_client):
        h = _bearer(user_id=env["admin_a"], tenant_id=env["ta"])
        await http_client.put("/api/admin/email-settings", headers=h, json={
            "sender_email": "x@y.com", "sender_name": "X",
            "api_key": "re_xxx", "status": "active",
        })
        r = await http_client.delete("/api/admin/email-settings", headers=h)
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "disabled"


# ────────────────────────────────────────────────────────────────────────
class TestResolveCredentials:
    async def test_returns_env_when_no_config(self, env, db):
        from services.tenant_email_settings import resolve_credentials
        with patch.dict(os.environ, {
            "RESEND_API_KEY": "env_key_global",
            "SENDER_EMAIL": "env@global.com",
            "SENDER_NAME": "Global",
        }, clear=False):
            with patch("core.config.RESEND_API_KEY", "env_key_global"), \
                 patch("core.config.SENDER_EMAIL", "env@global.com"), \
                 patch("core.config.SENDER_NAME", "Global"):
                creds = await resolve_credentials(env["ta"])
        assert creds["source"] == "env"
        assert creds["api_key"] == "env_key_global"

    async def test_returns_tenant_when_active(self, env, db):
        from services.tenant_email_settings import upsert, resolve_credentials
        await upsert(
            tenant_id=env["ta"], actor_id=env["admin_a"],
            sender_email="prod@empresa.com", sender_name="Empresa",
            api_key="re_tenant_real_xxx", status="active",
        )
        creds = await resolve_credentials(env["ta"])
        assert creds["source"] == "tenant"
        assert creds["api_key"] == "re_tenant_real_xxx"  # decrypted
        assert creds["sender_email"] == "prod@empresa.com"

    async def test_returns_env_when_tenant_disabled(self, env, db):
        from services.tenant_email_settings import upsert, resolve_credentials
        await upsert(
            tenant_id=env["ta"], actor_id=env["admin_a"],
            sender_email="prod@empresa.com", sender_name="Empresa",
            api_key="re_tenant_xxx", status="disabled",
        )
        creds = await resolve_credentials(env["ta"])
        assert creds["source"] == "env"


# ────────────────────────────────────────────────────────────────────────
class TestSendEmailUsesTenantCredentials:
    async def test_send_email_picks_tenant_key(self, env, db):
        """send_email(tenant_id=X) debe usar la API key del tenant X."""
        from services.tenant_email_settings import upsert
        from services import notification_service

        await upsert(
            tenant_id=env["ta"], actor_id=env["admin_a"],
            sender_email="prod@a.com", sender_name="A",
            api_key="re_TENANT_A_KEY", status="active",
        )
        captured = {}

        def fake_send(params):
            captured["params"] = params
            captured["api_key"] = notification_service.resend.api_key
            return {"id": "mock-msg-1"}

        with patch.object(notification_service.resend.Emails, "send",
                           side_effect=fake_send):
            result = await notification_service.send_email(
                to="dst@x.com", subject="hi", html="<p>hi</p>",
                tenant_id=env["ta"],
            )
        assert result.ok
        assert captured["api_key"] == "re_TENANT_A_KEY"
        assert captured["params"]["from"] == "A <prod@a.com>"

    async def test_send_email_test_endpoint_e2e(self, env, http_client, db):
        """Endpoint /test usa la key del tenant y registra el resultado."""
        from services.tenant_email_settings import upsert
        from services import notification_service

        await upsert(
            tenant_id=env["ta"], actor_id=env["admin_a"],
            sender_email="prod@a.com", sender_name="A",
            api_key="re_TENANT_KEY", status="active",
        )

        def fake_send(_params):
            return {"id": "msg-tenant-real"}

        with patch.object(notification_service.resend.Emails, "send",
                           side_effect=fake_send):
            h = _bearer(user_id=env["admin_a"], tenant_id=env["ta"])
            r = await http_client.post(
                "/api/admin/email-settings/test", headers=h,
                json={"to": "destino@x.com"},
            )
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["sent"] is True
        assert d["id"] == "msg-tenant-real"
        # Validar que se registró el resultado en BD
        doc = await db.tenant_email_settings.find_one(
            {"tenant_id": env["ta"]}, {"_id": 0})
        assert doc["last_test_ok"] is True
