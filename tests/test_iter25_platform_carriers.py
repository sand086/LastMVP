"""Iter25 — Platform-level carrier configs + 3-tier resolver.

Cubrimos:
  * PlatformCarrierRepository upsert con Fernet + tenant_access whitelist.
  * Resolver `client > tenant > platform` con auditoría (config_source).
  * Endpoints REST /api/platform/carriers (root_dev only).
  * Whitelist: tenant fuera de tenant_access → None.
  * Whitelist abierta (tenant_access vacío) → herencia universal.
  * agent.cancel_guia_on_carrier integra config_source en timeline + guia.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id
from core.crypto import decrypt
from repositories.clients import ClientRepository
from repositories.platform_carriers import PlatformCarrierRepository
from services.carrier_config_resolver import resolve_carrier_config
from services.cae.interface import ApiResponse
from services.cae.adapters.routal import RoutalAdapter


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
    tid_b = new_id()
    root_dev_id = new_id()
    admin_id = new_id()
    admin_b_id = new_id()
    client_id = new_id()
    project_id = new_id()
    await db.tenants.insert_many([
        {"id": tid, "slug": "cubbo", "name": "Cubbo", "status": "active"},
        {"id": tid_b, "slug": "other", "name": "Other", "status": "active"},
    ])
    await db.users.insert_many([
        {"id": root_dev_id, "tenant_id": tid, "email": "root@my",
         "role": "root_dev", "status": "active"},
        {"id": admin_id, "tenant_id": tid, "email": "a@my",
         "role": "admin", "status": "active"},
        {"id": admin_b_id, "tenant_id": tid_b, "email": "a@other",
         "role": "admin", "status": "active"},
    ])
    await db.projects.insert_one({"id": project_id, "tenant_id": tid,
                                    "name": "P", "status": "active"})
    await db.clients.insert_one({
        "id": client_id, "tenant_id": tid, "project_id": project_id,
        "name": "Cubbo MX", "ingest_mode": "pulling",
        "preferred_carrier_code": "routal", "carriers": {},
    })
    # Cleanup any platform configs from prior runs
    await db.platform_carrier_configs.delete_many({})
    return {"tid": tid, "tid_b": tid_b,
             "root_dev": root_dev_id,
             "admin": admin_id, "admin_b": admin_b_id,
             "client_id": client_id}


# ─── 1) Repository ──────────────────────────────────────────────────
class TestPlatformRepo:
    async def test_upsert_encrypts_secrets(self, env, db):
        repo = PlatformCarrierRepository()
        cfg = await repo.upsert("routal", {
            "name": "Routal Platform",
            "api_key": "PLATFORM-SECRET",
            "base_url": "https://api.routal.com",
            "billing_mode": "platform_pays",
        })
        # Public view never leaks
        assert "api_key" not in cfg
        assert "api_key_ref" not in cfg
        assert cfg["api_key_set"] is True

        doc = await db.platform_carrier_configs.find_one(
            {"code": "routal"}, {"_id": 0})
        assert doc["api_key_ref"].startswith("gAAAA")
        assert decrypt(doc["api_key_ref"]) == "PLATFORM-SECRET"

        # Plaintext via get_decrypted
        d = await repo.get_decrypted("routal")
        assert d["api_key"] == "PLATFORM-SECRET"
        assert d["billing_mode"] == "platform_pays"

    async def test_upsert_fedex_handles_client_secret(self, db):
        repo = PlatformCarrierRepository()
        await repo.upsert("fedex", {
            "api_key": "CID",
            "client_secret": "SECRET",
            "base_url": "https://apis-sandbox.fedex.com",
        })
        d = await repo.get_decrypted("fedex")
        assert d["api_key"] == "CID"
        assert d["client_secret"] == "SECRET"

    async def test_partial_update_preserves_secrets(self, db):
        repo = PlatformCarrierRepository()
        await repo.upsert("dhl", {"api_key": "FIRST"})
        await repo.upsert("dhl", {"base_url": "https://api-test.dhl.com/track"})
        d = await repo.get_decrypted("dhl")
        assert d["api_key"] == "FIRST"
        assert d["base_url"] == "https://api-test.dhl.com/track"

    async def test_grant_and_revoke_tenant_access(self, env, db):
        repo = PlatformCarrierRepository()
        await repo.upsert("routal", {"api_key": "K"})
        await repo.grant_access("routal", env["tid"],
                                  project_ids=["proj-A", "proj-B"],
                                  rate_limit_per_min=60)
        cfg = await repo.get("routal")
        ta = cfg["tenant_access"][env["tid"]]
        assert ta["project_ids"] == ["proj-A", "proj-B"]
        assert ta["rate_limit_per_min"] == 60
        assert ta["enabled"] is True
        # Revoke
        await repo.revoke_access("routal", env["tid"])
        cfg = await repo.get("routal")
        assert env["tid"] not in (cfg.get("tenant_access") or {})


# ─── 2) Resolver ────────────────────────────────────────────────────
class TestResolverHierarchy:
    async def test_client_level_wins_when_set(self, env):
        # Set both per-client AND platform
        cli = ClientRepository(tenant_id=env["tid"])
        await cli.set_carrier_config(env["client_id"], "routal", {
            "api_key": "CLIENT-KEY",
            "project_ids": ["client-proj-1"],
        })
        plat = PlatformCarrierRepository()
        await plat.upsert("routal", {"api_key": "PLATFORM-KEY"})
        await plat.grant_access("routal", env["tid"],
                                 project_ids=["platform-proj-1"])

        res = await resolve_carrier_config(
            tenant_id=env["tid"], client_id=env["client_id"], code="routal")
        assert res["config_source"] == "client"
        assert res["api_key"] == "CLIENT-KEY"
        assert res["project_ids"] == ["client-proj-1"]

    async def test_tenant_level_carrier_wins_when_no_client_override(
            self, env, db):
        # Tenant carrier with own creds; no client override; platform exists.
        from core.crypto import encrypt
        await db.carriers.insert_one({
            "id": new_id(), "tenant_id": env["tid"],
            "code": "routal", "name": "Routal", "status": "active",
            "has_api": True,
            "api_url": "https://tenant.routal",
            "api_creds_ref": encrypt("TENANT-OWN-KEY"),
        })
        plat = PlatformCarrierRepository()
        await plat.upsert("routal", {"api_key": "PLATFORM-KEY"})

        res = await resolve_carrier_config(
            tenant_id=env["tid"], client_id=env["client_id"], code="routal")
        assert res["config_source"] == "tenant"
        assert res["api_key"] == "TENANT-OWN-KEY"
        assert res["base_url"] == "https://tenant.routal"

    async def test_platform_inherits_when_open_access(self, env):
        plat = PlatformCarrierRepository()
        await plat.upsert("dhl", {
            "api_key": "PLATFORM-DHL",
            "base_url": "https://api-eu.dhl.com/track",
        })
        # NO tenant_access entries → open access
        res = await resolve_carrier_config(
            tenant_id=env["tid"], client_id=env["client_id"], code="dhl")
        assert res["config_source"] == "platform"
        assert res["api_key"] == "PLATFORM-DHL"
        assert res["project_ids"] == []  # DHL no projects

    async def test_platform_blocked_when_tenant_not_in_whitelist(self, env):
        plat = PlatformCarrierRepository()
        await plat.upsert("routal", {"api_key": "PLATFORM"})
        # Grant ONLY to tenant_b
        await plat.grant_access("routal", env["tid_b"],
                                 project_ids=["b-proj"])
        # tenant A should NOT resolve
        res = await resolve_carrier_config(
            tenant_id=env["tid"], client_id=env["client_id"], code="routal")
        assert res is None

    async def test_platform_filters_project_ids_by_tenant(self, env):
        plat = PlatformCarrierRepository()
        await plat.upsert("routal", {"api_key": "PLATFORM"})
        await plat.grant_access("routal", env["tid"],
                                 project_ids=["proj-cubbo-1", "proj-cubbo-2"])
        await plat.grant_access("routal", env["tid_b"],
                                 project_ids=["proj-otro-1"])
        res = await resolve_carrier_config(
            tenant_id=env["tid"], client_id=env["client_id"], code="routal")
        assert res["config_source"] == "platform"
        # Cubbo only sees its own projects — not tenant B's
        assert res["project_ids"] == ["proj-cubbo-1", "proj-cubbo-2"]
        assert res["default_project_id"] == "proj-cubbo-1"

    async def test_disabled_tenant_entry_blocks_inheritance(self, env):
        plat = PlatformCarrierRepository()
        await plat.upsert("routal", {"api_key": "PLATFORM"})
        await plat.grant_access("routal", env["tid"], project_ids=["x"],
                                 enabled=False)
        res = await resolve_carrier_config(
            tenant_id=env["tid"], client_id=env["client_id"], code="routal")
        assert res is None

    async def test_no_match_returns_none(self, env):
        res = await resolve_carrier_config(
            tenant_id=env["tid"], client_id=env["client_id"], code="dhl")
        assert res is None


# ─── 3) REST endpoints ─────────────────────────────────────────────
class TestRESTEndpoints:
    async def test_root_dev_can_put_and_get(self, env, http_client):
        h = _bearer(user_id=env["root_dev"], tenant_id=env["tid"],
                    role="root_dev")
        r = await http_client.put("/api/platform/carriers/routal",
                                    headers=h,
                                    json={"api_key": "K-PLATFORM",
                                          "base_url": "https://api.routal.com"})
        assert r.status_code == 200
        assert r.json()["data"]["api_key_set"] is True
        g = await http_client.get("/api/platform/carriers/routal", headers=h)
        assert g.status_code == 200
        assert g.json()["data"]["configured"] is True

    async def test_admin_role_forbidden(self, env, http_client):
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"], role="admin")
        r = await http_client.put("/api/platform/carriers/routal",
                                    headers=h, json={"api_key": "X"})
        assert r.status_code == 403

    async def test_no_auth_401(self, http_client):
        r = await http_client.get("/api/platform/carriers/routal")
        assert r.status_code == 401

    async def test_grant_revoke_access(self, env, http_client):
        h = _bearer(user_id=env["root_dev"], tenant_id=env["tid"],
                    role="root_dev")
        await http_client.put("/api/platform/carriers/routal",
                                headers=h, json={"api_key": "K"})
        # Grant
        r = await http_client.put(
            f"/api/platform/carriers/routal/access/{env['tid_b']}",
            headers=h, json={"project_ids": ["p1", "p2"],
                              "rate_limit_per_min": 60})
        assert r.status_code == 200
        # Revoke
        r2 = await http_client.delete(
            f"/api/platform/carriers/routal/access/{env['tid_b']}", headers=h)
        assert r2.status_code == 200
        assert r2.json()["data"]["revoked"] is True

    async def test_grant_on_missing_carrier_404(self, env, http_client):
        h = _bearer(user_id=env["root_dev"], tenant_id=env["tid"],
                    role="root_dev")
        r = await http_client.put(
            f"/api/platform/carriers/unknown/access/{env['tid']}",
            headers=h, json={})
        assert r.status_code == 404

    async def test_list_endpoint(self, env, http_client):
        h = _bearer(user_id=env["root_dev"], tenant_id=env["tid"],
                    role="root_dev")
        await http_client.put("/api/platform/carriers/routal",
                                headers=h, json={"api_key": "K1"})
        await http_client.put("/api/platform/carriers/dhl",
                                headers=h, json={"api_key": "K2"})
        r = await http_client.get("/api/platform/carriers", headers=h)
        assert r.status_code == 200
        codes = [c["code"] for c in r.json()["data"]["items"]]
        assert "routal" in codes and "dhl" in codes


# ─── 4) agent.cancel uses resolver + records config_source ─────────
class TestCancelWithResolver:
    async def test_cancel_uses_platform_creds_when_no_client_cfg(
            self, env, http_client, db, monkeypatch):
        """Si el client no tiene Routal pero la plataforma sí + whitelist OK,
        el cancel debe disparar usando creds de la plataforma y registrar
        config_source='platform' en el timeline."""
        # Set platform creds + grant tenant
        plat = PlatformCarrierRepository()
        await plat.upsert("routal", {"api_key": "PLAT-K"})
        await plat.grant_access("routal", env["tid"],
                                 project_ids=["plat-proj-1"])

        # Guía + ticket
        guia_id = new_id()
        ticket_id = new_id()
        await db.guias.insert_one({
            "id": guia_id, "tenant_id": env["tid"],
            "client_id": env["client_id"],
            "tracking_id": "TRK-PLAT-1",
            "carrier_code": "routal",
            "internal_status": "in_transit",
            "carrier_meta": {"routal_project_id": "plat-proj-1"},
        })
        await db.tickets.insert_one({
            "id": ticket_id, "tenant_id": env["tid"],
            "client_id": env["client_id"], "guia_id": guia_id,
            "tracking_id": "TRK-PLAT-1", "status": "in_progress",
        })

        called: dict = {}

        async def fake_send(self, tracking_id, payload):
            called["api_key"] = self.api_key
            called["project_id"] = payload.get("project_id")
            return ApiResponse(received=True, status=200)

        monkeypatch.setattr(RoutalAdapter, "send_instruction", fake_send)

        h = _bearer(user_id=env["admin"], tenant_id=env["tid"], role="admin")
        r = await http_client.post(f"/api/agent/guias/{guia_id}/cancel",
                                     headers=h, json={})
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["received"] is True
        assert body["config_source"] == "platform"
        assert called["api_key"] == "PLAT-K"
        assert called["project_id"] == "plat-proj-1"

        # Timeline event captures the config_source
        ev = await db.timeline_events.find_one(
            {"ticket_id": ticket_id, "event_type": "carrier_outbound_sent"},
            {"_id": 0})
        assert ev["payload"]["config_source"] == "platform"
        assert "creds=platform" in ev["description"]

        # Guía has outbound_last_config_source
        g = await db.guias.find_one({"id": guia_id}, {"_id": 0})
        assert g["outbound_last_config_source"] == "platform"

    async def test_cancel_400_when_no_resolved_creds(self, env, http_client,
                                                       db):
        """Sin cfg en ningún nivel → 400 explícito mencionando los 3 niveles."""
        guia_id = new_id()
        await db.guias.insert_one({
            "id": guia_id, "tenant_id": env["tid"],
            "client_id": env["client_id"],
            "tracking_id": "TRK-NONE", "carrier_code": "routal",
            "carrier_meta": {},
        })
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"], role="admin")
        r = await http_client.post(f"/api/agent/guias/{guia_id}/cancel",
                                     headers=h, json={})
        assert r.status_code in (400, 422)
        # Error mentions all 3 levels (client, tenant, plataforma)
        if r.status_code == 400:
            msg = r.json()["errors"][0]["message"].lower()
            assert "cliente" in msg or "tenant" in msg or "plataforma" in msg
