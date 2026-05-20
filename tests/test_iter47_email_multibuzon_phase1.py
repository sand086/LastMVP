"""Iter47 · Bundle G — Email Multi-Buzón (FASE 1 backend + migración).

Cubre:
  - Migración backward-compatible mono-buzón → multi-buzón.
  - EmailDispatcher.resolve_mailbox() — algoritmo de especificidad (E2.2).
  - EmailDispatcher.send() — R53 fail-loud, quota, dominio degradado.
  - Aislamiento por tenant en las 4 colecciones nuevas.
  - email_send_log append-only con subject_hash + to_masked (PII).
"""
from __future__ import annotations
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from core.crypto import encrypt
from core.uuid import new_id
from models.email_multibuzon import EmailContext, EmailPayload
from services.email_dispatcher import EmailDispatcher
from services.email_multibuzon_migration import migrate_tenant


# ─────────────────────────────────────────────────────────────
@pytest.fixture
async def env(db):
    """Setup: 1 tenant + 1 client + 1 dominio verificado + 1 mailbox default."""
    tid = new_id()
    cid_a = new_id()
    cid_b = new_id()
    await db.tenants.insert_one({
        "id": tid, "slug": "g-mb", "name": "T-MB", "status": "active",
    })
    await db.clients.insert_many([
        {"id": cid_a, "tenant_id": tid, "name": "Cliente A",
         "status": "active", "ingest_mode": "webhook"},
        {"id": cid_b, "tenant_id": tid, "name": "Cliente B",
         "status": "active", "ingest_mode": "webhook"},
    ])
    return {"tid": tid, "cl_a": cid_a, "cl_b": cid_b}


def _make_domain(tid, *, verified=True, degraded=False):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": new_id(), "tenant_id": tid, "domain": "mye.com",
        "provider": "resend", "verification_status": "verified" if verified else "pending",
        "dkim_verified": verified, "spf_verified": verified, "dmarc_verified": verified,
        "verified_at": now if verified else None,
        "degraded": degraded, "created_by": "test",
        "created_at": now, "updated_at": now,
    }


def _make_mailbox(tid, did, *, client_id=None, active=True,
                   default_tenant=False, default_client=False,
                   api_key="re_test_xxxx"):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": new_id(), "tenant_id": tid, "client_id": client_id,
        "domain_id": did, "display_name": "MB", "sender_name": "MyE",
        "sender_email": "noreply@mye.com", "reply_to_email": None,
        "is_active": active, "is_default_for_tenant": default_tenant,
        "is_default_for_client": default_client, "daily_send_limit": None,
        "monthly_send_count": 0, "workflow_types": ["generic"],
        "api_key_ref": encrypt(api_key), "api_key_last4": api_key[-4:],
        "created_by": "test", "created_at": now, "updated_at": now,
    }


def _make_routing(tid, mb_id, *, workflow_type="generic", client_id=None,
                   motivo_id=None, priority=100):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": new_id(), "tenant_id": tid, "mailbox_id": mb_id,
        "workflow_type": workflow_type, "client_id": client_id,
        "motivo_id": motivo_id, "priority": priority, "active": True,
        "description": "", "created_at": now, "updated_at": now,
    }


# ─────────────────────────────────────────────────────────────
# Test 1 · MIGRACIÓN backward-compatible
# ─────────────────────────────────────────────────────────────
class TestMigration:
    async def test_migrates_active_legacy_config(self, env, db):
        # Sembrar legacy
        await db.tenant_email_settings.insert_one({
            "tenant_id": env["tid"], "sender_email": "info@mye.com",
            "sender_name": "MyE", "reply_to_default": "hola@mye.com",
            "status": "active",
            "api_key_ref": encrypt("re_legacy_key_xyz"),
            "api_key_last4": "_xyz",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        result = await migrate_tenant(env["tid"])
        assert result["status"] == "migrated"
        # Verificar las 3 filas creadas
        dom = await db.email_domains.find_one({"id": result["domain_id"]}, {"_id": 0})
        assert dom["domain"] == "mye.com"
        assert dom["verification_status"] == "verified"
        mb = await db.email_mailboxes.find_one({"id": result["mailbox_id"]}, {"_id": 0})
        assert mb["is_default_for_tenant"] is True
        assert mb["sender_email"] == "info@mye.com"
        rt = await db.email_routing.find_one({"id": result["routing_id"]}, {"_id": 0})
        assert rt["workflow_type"] == "generic"
        # Legacy marcado pero NO borrado
        legacy = await db.tenant_email_settings.find_one(
            {"tenant_id": env["tid"]}, {"_id": 0})
        assert legacy["migrated_to_multibuzon"] is True
        assert legacy["sender_email"] == "info@mye.com"  # preservado

    async def test_idempotent_skips_when_already_migrated(self, env, db):
        await db.tenant_email_settings.insert_one({
            "tenant_id": env["tid"], "sender_email": "info@mye.com",
            "sender_name": "MyE", "status": "active",
            "api_key_ref": encrypt("re_xxx"), "api_key_last4": "_xxx",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        r1 = await migrate_tenant(env["tid"])
        assert r1["status"] == "migrated"
        # Segunda corrida no debe duplicar
        r2 = await migrate_tenant(env["tid"])
        assert r2["status"] == "skipped_already_done"
        count = await db.email_mailboxes.count_documents(
            {"tenant_id": env["tid"]})
        assert count == 1

    async def test_skips_when_no_legacy(self, env, db):
        r = await migrate_tenant(env["tid"])
        assert r["status"] == "skipped_no_legacy"

    async def test_skips_disabled_legacy(self, env, db):
        await db.tenant_email_settings.insert_one({
            "tenant_id": env["tid"], "sender_email": "x@mye.com",
            "sender_name": "MyE", "status": "disabled",
            "api_key_ref": encrypt("re_xxx"), "api_key_last4": "_xxx",
        })
        r = await migrate_tenant(env["tid"])
        assert r["status"] == "skipped_inactive"


# ─────────────────────────────────────────────────────────────
# Test 2 · RESOLUCIÓN de buzón (E2.2)
# ─────────────────────────────────────────────────────────────
class TestResolveMailbox:
    async def test_default_tenant_when_no_rule(self, env, db):
        dom = _make_domain(env["tid"])
        mb = _make_mailbox(env["tid"], dom["id"], default_tenant=True)
        await db.email_domains.insert_one(dom)
        await db.email_mailboxes.insert_one(mb)
        d = EmailDispatcher(env["tid"])
        ctx = EmailContext(tenant_id=env["tid"], workflow_type="generic")
        resolved = await d.resolve_mailbox(ctx)
        assert resolved["id"] == mb["id"]

    async def test_client_default_wins_over_tenant_default(self, env, db):
        dom = _make_domain(env["tid"])
        mb_t = _make_mailbox(env["tid"], dom["id"], default_tenant=True)
        mb_c = _make_mailbox(env["tid"], dom["id"], client_id=env["cl_a"],
                              default_client=True)
        await db.email_domains.insert_one(dom)
        await db.email_mailboxes.insert_many([mb_t, mb_c])
        d = EmailDispatcher(env["tid"])
        ctx = EmailContext(tenant_id=env["tid"], workflow_type="generic",
                           client_id=env["cl_a"])
        resolved = await d.resolve_mailbox(ctx)
        assert resolved["id"] == mb_c["id"]

    async def test_routing_rule_wins_over_defaults(self, env, db):
        dom = _make_domain(env["tid"])
        mb_default = _make_mailbox(env["tid"], dom["id"], default_tenant=True)
        mb_special = _make_mailbox(env["tid"], dom["id"])
        rt = _make_routing(env["tid"], mb_special["id"],
                            workflow_type="claim_communication",
                            client_id=env["cl_a"], priority=200)
        await db.email_domains.insert_one(dom)
        await db.email_mailboxes.insert_many([mb_default, mb_special])
        await db.email_routing.insert_one(rt)
        d = EmailDispatcher(env["tid"])
        ctx = EmailContext(tenant_id=env["tid"],
                           workflow_type="claim_communication",
                           client_id=env["cl_a"])
        resolved = await d.resolve_mailbox(ctx)
        assert resolved["id"] == mb_special["id"]

    async def test_more_specific_rule_wins(self, env, db):
        dom = _make_domain(env["tid"])
        mb_a = _make_mailbox(env["tid"], dom["id"])
        mb_b = _make_mailbox(env["tid"], dom["id"])
        # Regla A: workflow + client (especificidad=1)
        rt_a = _make_routing(env["tid"], mb_a["id"],
                              workflow_type="ticket_notification",
                              client_id=env["cl_a"], priority=100)
        # Regla B: workflow + client + motivo (especificidad=2)
        motivo_id = new_id()
        rt_b = _make_routing(env["tid"], mb_b["id"],
                              workflow_type="ticket_notification",
                              client_id=env["cl_a"], motivo_id=motivo_id,
                              priority=50)
        await db.email_domains.insert_one(dom)
        await db.email_mailboxes.insert_many([mb_a, mb_b])
        await db.email_routing.insert_many([rt_a, rt_b])
        d = EmailDispatcher(env["tid"])
        ctx = EmailContext(tenant_id=env["tid"],
                           workflow_type="ticket_notification",
                           client_id=env["cl_a"], motivo_id=motivo_id)
        resolved = await d.resolve_mailbox(ctx)
        assert resolved["id"] == mb_b["id"]  # más específica gana aunque priority menor

    async def test_no_match_returns_none(self, env, db):
        d = EmailDispatcher(env["tid"])
        ctx = EmailContext(tenant_id=env["tid"], workflow_type="generic")
        resolved = await d.resolve_mailbox(ctx)
        assert resolved is None

    async def test_inactive_mailbox_in_rule_is_ignored(self, env, db):
        dom = _make_domain(env["tid"])
        mb_off = _make_mailbox(env["tid"], dom["id"], active=False)
        mb_default = _make_mailbox(env["tid"], dom["id"], default_tenant=True)
        rt = _make_routing(env["tid"], mb_off["id"],
                            workflow_type="generic", priority=200)
        await db.email_domains.insert_one(dom)
        await db.email_mailboxes.insert_many([mb_off, mb_default])
        await db.email_routing.insert_one(rt)
        d = EmailDispatcher(env["tid"])
        ctx = EmailContext(tenant_id=env["tid"], workflow_type="generic")
        resolved = await d.resolve_mailbox(ctx)
        # Cae al default del tenant porque el mailbox de la regla está apagado
        assert resolved["id"] == mb_default["id"]

    async def test_explicit_mailbox_id_override(self, env, db):
        dom = _make_domain(env["tid"])
        mb_default = _make_mailbox(env["tid"], dom["id"], default_tenant=True)
        mb_override = _make_mailbox(env["tid"], dom["id"])
        await db.email_domains.insert_one(dom)
        await db.email_mailboxes.insert_many([mb_default, mb_override])
        d = EmailDispatcher(env["tid"])
        ctx = EmailContext(tenant_id=env["tid"], workflow_type="generic",
                           explicit_mailbox_id=mb_override["id"])
        resolved = await d.resolve_mailbox(ctx)
        assert resolved["id"] == mb_override["id"]


# ─────────────────────────────────────────────────────────────
# Test 3 · SEND con R53 fail-loud
# ─────────────────────────────────────────────────────────────
class TestSend:
    async def test_no_mailbox_resolved_fails_visibly(self, env, db):
        d = EmailDispatcher(env["tid"])
        ctx = EmailContext(tenant_id=env["tid"], workflow_type="generic")
        payload = EmailPayload(to=["x@y.com"], subject="hi", body_html="<p>hi</p>")
        result = await d.send(ctx, payload)
        assert result.success is False
        assert result.error_code == "NO_MAILBOX_RESOLVED"
        # Append-only: el log queda registrado
        rec = await db.email_send_log.find_one({"id": result.log_id}, {"_id": 0})
        assert rec["status"] == "failed"
        assert rec["error_code"] == "NO_MAILBOX_RESOLVED"
        assert rec["subject_hash"]  # PII: hash, no plaintext
        assert "@" not in rec["subject_hash"]
        assert "***@" in rec["to_masked"]

    async def test_unverified_domain_fails(self, env, db):
        dom = _make_domain(env["tid"], verified=False)
        mb = _make_mailbox(env["tid"], dom["id"], default_tenant=True)
        await db.email_domains.insert_one(dom)
        await db.email_mailboxes.insert_one(mb)
        d = EmailDispatcher(env["tid"])
        ctx = EmailContext(tenant_id=env["tid"], workflow_type="generic")
        payload = EmailPayload(to=["x@y.com"], subject="hi", body_html="<p>hi</p>")
        result = await d.send(ctx, payload)
        assert result.success is False
        assert result.error_code == "DOMAIN_NOT_VERIFIED"

    async def test_degraded_domain_fails(self, env, db):
        dom = _make_domain(env["tid"], verified=True, degraded=True)
        mb = _make_mailbox(env["tid"], dom["id"], default_tenant=True)
        await db.email_domains.insert_one(dom)
        await db.email_mailboxes.insert_one(mb)
        d = EmailDispatcher(env["tid"])
        ctx = EmailContext(tenant_id=env["tid"], workflow_type="generic")
        payload = EmailPayload(to=["x@y.com"], subject="hi", body_html="<p>hi</p>")
        result = await d.send(ctx, payload)
        assert result.success is False
        assert result.error_code == "DOMAIN_NOT_VERIFIED"

    async def test_quota_exceeded_blocks_send(self, env, db):
        dom = _make_domain(env["tid"])
        mb = _make_mailbox(env["tid"], dom["id"], default_tenant=True)
        mb["daily_send_limit"] = 1
        await db.email_domains.insert_one(dom)
        await db.email_mailboxes.insert_one(mb)
        # Sembrar un envío de hoy
        today = datetime.now(timezone.utc).isoformat()
        await db.email_send_log.insert_one({
            "id": new_id(), "tenant_id": env["tid"], "mailbox_id": mb["id"],
            "workflow_type": "generic", "subject_hash": "x", "to_masked": "y",
            "status": "sent", "sent_at": today, "client_id": None,
        })
        d = EmailDispatcher(env["tid"])
        ctx = EmailContext(tenant_id=env["tid"], workflow_type="generic")
        payload = EmailPayload(to=["x@y.com"], subject="hi", body_html="<p>hi</p>")
        result = await d.send(ctx, payload)
        assert result.success is False
        assert result.error_code == "QUOTA_EXCEEDED"

    async def test_send_success_with_mock_resend(self, env, db):
        dom = _make_domain(env["tid"])
        mb = _make_mailbox(env["tid"], dom["id"], default_tenant=True)
        await db.email_domains.insert_one(dom)
        await db.email_mailboxes.insert_one(mb)
        captured = {}

        def fake_send(params):
            captured["params"] = params
            return {"id": "msg_real_123"}

        with patch("services.email_dispatcher.EmailDispatcher._send_via_resend") as m:
            async def _fake(**kwargs):
                fake_send(kwargs)
                return {"ok": True, "id": "msg_real_123"}
            m.side_effect = _fake
            d = EmailDispatcher(env["tid"])
            ctx = EmailContext(tenant_id=env["tid"], workflow_type="generic")
            payload = EmailPayload(to=["x@y.com"], subject="hello",
                                    body_html="<p>hello</p>")
            result = await d.send(ctx, payload)
        assert result.success is True
        assert result.provider_message_id == "msg_real_123"
        # Mailbox monthly_send_count incrementado
        mb_after = await db.email_mailboxes.find_one({"id": mb["id"]}, {"_id": 0})
        assert mb_after["monthly_send_count"] == 1
        # Log append-only con status=sent
        log_row = await db.email_send_log.find_one({"id": result.log_id}, {"_id": 0})
        assert log_row["status"] == "sent"
        assert log_row["provider_message_id"] == "msg_real_123"


# ─────────────────────────────────────────────────────────────
# Test 4 · Aislamiento por tenant
# ─────────────────────────────────────────────────────────────
class TestTenantIsolation:
    async def test_tenant_a_cannot_resolve_tenant_b_mailbox(self, env, db):
        # Crear tenant B con su propio mailbox default
        tb = new_id()
        await db.tenants.insert_one(
            {"id": tb, "slug": "ot", "name": "T-B", "status": "active"})
        dom_b = _make_domain(tb)
        mb_b = _make_mailbox(tb, dom_b["id"], default_tenant=True)
        await db.email_domains.insert_one(dom_b)
        await db.email_mailboxes.insert_one(mb_b)
        # Tenant A intenta resolver SU contexto → no debe encontrar B
        d_a = EmailDispatcher(env["tid"])
        ctx = EmailContext(tenant_id=env["tid"], workflow_type="generic")
        resolved = await d_a.resolve_mailbox(ctx)
        assert resolved is None

    async def test_explicit_mailbox_id_of_other_tenant_denied(self, env, db):
        tb = new_id()
        await db.tenants.insert_one(
            {"id": tb, "slug": "ot2", "name": "T-B2", "status": "active"})
        dom_b = _make_domain(tb)
        mb_b = _make_mailbox(tb, dom_b["id"])
        await db.email_domains.insert_one(dom_b)
        await db.email_mailboxes.insert_one(mb_b)
        # Tenant A pasa el mailbox_id de B como explicit override
        d_a = EmailDispatcher(env["tid"])
        ctx = EmailContext(tenant_id=env["tid"], workflow_type="generic",
                           explicit_mailbox_id=mb_b["id"])
        # El scope del repo filtra por tenant_id, así que no aparece
        assert await d_a.resolve_mailbox(ctx) is None
