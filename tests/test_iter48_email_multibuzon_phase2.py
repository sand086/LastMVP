"""Iter48 · Bundle G FASE 2 — Endpoints admin email multi-buzón."""
from __future__ import annotations
import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.crypto import encrypt
from core.security import create_access_token, hash_password
from core.uuid import new_id


def _bearer(*, user_id, tenant_id, role="admin", email="admin@t.io"):
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
    tid = new_id()
    cid = new_id()
    admin_id = new_id()
    agent_id = new_id()
    await db.tenants.insert_one({"id": tid, "slug": "ph2", "name": "T-Ph2",
                                  "status": "active"})
    await db.clients.insert_one({"id": cid, "tenant_id": tid, "name": "Cl",
                                  "status": "active", "ingest_mode": "webhook"})
    await db.users.insert_many([
        {"id": admin_id, "tenant_id": tid, "email": "admin@ph2.io",
         "role": "admin", "status": "active", "password_hash": hash_password("x")},
        {"id": agent_id, "tenant_id": tid, "email": "agent@ph2.io",
         "role": "agent", "status": "active", "password_hash": hash_password("x")},
    ])
    return {"tid": tid, "cl": cid, "admin": admin_id, "agent": agent_id}


# ─────────────────────────────────────────────────────────────
class TestDomainEndpoints:
    async def test_full_domain_lifecycle(self, env, http_client):
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"])
        # Create
        r = await http_client.post("/api/admin/email/domains",
                                    headers=h, json={"domain": "envios.mye.com"})
        assert r.status_code == 201
        did = r.json()["data"]["id"]
        assert r.json()["data"]["verification_status"] == "pending"
        assert len(r.json()["data"]["dns_records"]) >= 3
        # List
        r2 = await http_client.get("/api/admin/email/domains", headers=h)
        assert r2.json()["data"]["count"] == 1
        # Verify
        r3 = await http_client.post(f"/api/admin/email/domains/{did}/verify",
                                     headers=h)
        assert r3.json()["data"]["verification_status"] == "verified"
        # Delete (no mailbox using it)
        r4 = await http_client.delete(f"/api/admin/email/domains/{did}",
                                       headers=h)
        assert r4.status_code == 200

    async def test_duplicate_domain_rejected(self, env, http_client):
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"])
        await http_client.post("/api/admin/email/domains",
                                headers=h, json={"domain": "x.com"})
        r = await http_client.post("/api/admin/email/domains",
                                    headers=h, json={"domain": "x.com"})
        assert r.status_code == 422

    async def test_agent_forbidden(self, env, http_client):
        h = _bearer(user_id=env["agent"], tenant_id=env["tid"], role="agent",
                    email="agent@ph2.io")
        r = await http_client.get("/api/admin/email/domains", headers=h)
        assert r.status_code == 403


# ─────────────────────────────────────────────────────────────
class TestMailboxEndpoints:
    async def test_create_mailbox_validates_domain_email_match(self, env, http_client, db):
        # Create + verify domain
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"])
        r1 = await http_client.post("/api/admin/email/domains",
                                     headers=h, json={"domain": "mye.com"})
        did = r1.json()["data"]["id"]
        await http_client.post(f"/api/admin/email/domains/{did}/verify",
                                headers=h)
        # Sender email NOT belongs to domain → 422
        bad = await http_client.post("/api/admin/email/mailboxes", headers=h, json={
            "domain_id": did, "display_name": "X", "sender_name": "X",
            "sender_email": "x@otrodominio.com",
        })
        assert bad.status_code == 422
        # Sender ok
        ok = await http_client.post("/api/admin/email/mailboxes", headers=h, json={
            "domain_id": did, "display_name": "MB1", "sender_name": "MyE",
            "sender_email": "soporte@mye.com",
            "api_key": "re_test_xyz_1234",
            "is_default_for_tenant": True,
        })
        assert ok.status_code == 201
        d = ok.json()["data"]
        assert d["is_default_for_tenant"] is True
        assert d["api_key_last4"] == "1234"

    async def test_setting_new_default_clears_old(self, env, http_client, db):
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"])
        r1 = await http_client.post("/api/admin/email/domains",
                                     headers=h, json={"domain": "z.com"})
        did = r1.json()["data"]["id"]
        await http_client.post(f"/api/admin/email/domains/{did}/verify", headers=h)
        # MB1 default
        mb1 = await http_client.post("/api/admin/email/mailboxes", headers=h, json={
            "domain_id": did, "display_name": "MB1", "sender_name": "MyE",
            "sender_email": "a@z.com", "is_default_for_tenant": True,
        })
        # MB2 también default → MB1 debe dejar de serlo
        mb2 = await http_client.post("/api/admin/email/mailboxes", headers=h, json={
            "domain_id": did, "display_name": "MB2", "sender_name": "MyE",
            "sender_email": "b@z.com", "is_default_for_tenant": True,
        })
        assert mb2.status_code == 201
        # Verificar
        r = await http_client.get("/api/admin/email/mailboxes", headers=h)
        items = r.json()["data"]["items"]
        defaults = [m for m in items if m["is_default_for_tenant"]]
        assert len(defaults) == 1
        assert defaults[0]["id"] == mb2.json()["data"]["id"]

    async def test_cannot_delete_last_mailbox(self, env, http_client):
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"])
        r1 = await http_client.post("/api/admin/email/domains",
                                     headers=h, json={"domain": "last.com"})
        did = r1.json()["data"]["id"]
        await http_client.post(f"/api/admin/email/domains/{did}/verify", headers=h)
        mb = await http_client.post("/api/admin/email/mailboxes", headers=h, json={
            "domain_id": did, "display_name": "Only", "sender_name": "X",
            "sender_email": "x@last.com",
        })
        mb_id = mb.json()["data"]["id"]
        r = await http_client.delete(f"/api/admin/email/mailboxes/{mb_id}",
                                      headers=h)
        assert r.status_code == 422
        assert "último" in r.json()["errors"][0]["message"].lower()


# ─────────────────────────────────────────────────────────────
class TestExplainEndpoint:
    async def test_explain_returns_resolved_and_rules(self, env, http_client, db):
        # Sembrar dominio + mailbox + rule
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        did = new_id()
        mid = new_id()
        rid = new_id()
        await db.email_domains.insert_one({
            "id": did, "tenant_id": env["tid"], "domain": "x.com",
            "verification_status": "verified", "degraded": False,
            "created_at": now, "updated_at": now,
        })
        await db.email_mailboxes.insert_one({
            "id": mid, "tenant_id": env["tid"], "client_id": None,
            "domain_id": did, "display_name": "MB", "sender_name": "MyE",
            "sender_email": "x@x.com", "is_active": True,
            "is_default_for_tenant": True, "is_default_for_client": False,
            "workflow_types": ["generic"], "api_key_ref": encrypt("re_xxx"),
            "api_key_last4": "_xxx", "monthly_send_count": 0,
            "created_at": now, "updated_at": now,
        })
        await db.email_routing.insert_one({
            "id": rid, "tenant_id": env["tid"], "mailbox_id": mid,
            "workflow_type": "ticket_notification", "client_id": None,
            "motivo_id": None, "priority": 50, "active": True,
            "description": "", "created_at": now, "updated_at": now,
        })
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"])
        r = await http_client.post("/api/admin/email/explain", headers=h, json={
            "workflow_type": "ticket_notification",
        })
        d = r.json()["data"]
        assert d["resolved_mailbox"]["id"] == mid
        assert len(d["matched_rules"]) == 1

    async def test_explain_returns_none_when_no_config(self, env, http_client):
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"])
        r = await http_client.post("/api/admin/email/explain", headers=h, json={
            "workflow_type": "ticket_notification",
        })
        assert r.json()["data"]["resolved_mailbox"] is None


# ─────────────────────────────────────────────────────────────
class TestHealthEndpoint:
    async def test_health_aggregates_correctly(self, env, http_client, db):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        # Sembrar 3 logs: 2 sent, 1 failed
        for status, code in [("sent", None), ("sent", None),
                              ("failed", "DOMAIN_NOT_VERIFIED")]:
            await db.email_send_log.insert_one({
                "id": new_id(), "tenant_id": env["tid"],
                "mailbox_id": new_id(),
                "workflow_type": "generic", "to_masked": "x***@y.com",
                "subject_hash": "hash", "status": status,
                "error_code": code, "sent_at": now,
            })
        h = _bearer(user_id=env["admin"], tenant_id=env["tid"])
        r = await http_client.get("/api/admin/email/health?days=7", headers=h)
        d = r.json()["data"]
        assert d["total"] == 3
        assert d["sent"] == 2
        assert d["failed"] == 1
        assert d["errors_by_code"][0]["code"] == "DOMAIN_NOT_VERIFIED"
        assert abs(d["delivery_rate"] - 2/3) < 0.01
