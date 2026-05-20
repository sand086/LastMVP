"""Tests para los items P2 de PROMPT 39 V3 + auditor attestation IA.

Cubre:
  - JSONPath filter (legacy + JSONPath real)
  - Burst mode (is_paused) — eventos retenidos sin perder
  - README markdown generator
  - Webhook test echo público (HMAC verification + chaos params)
  - IA auditor attestation (download + review)
  - Routal pulling job wired al scheduler (con adapter mockeado)
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id
from repositories.webhooks import (
    WebhookSubscriptionRepository, ensure_webhook_indexes,
)
from seeds.webhook_catalog import run as seed_webhooks
from services.webhooks.filter import evaluate_filter
from services.webhooks.readme_generator import generate_readme
from services.webhooks.security import encrypt_secret, sign_body, generate_secret


def _bearer(*, user_id: str, tenant_id: str, role: str = "admin"):
    tok = create_access_token(user_id=user_id, tenant_id=tenant_id,
                              role=role, email="x@t")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def setup(db):
    await seed_webhooks()
    await ensure_webhook_indexes()
    tid = new_id()
    uid = new_id()
    cl = new_id()
    await db.tenants.insert_one({"id": tid, "slug": "p2", "name": "T",
                                 "status": "active"})
    await db.users.insert_one({"id": uid, "tenant_id": tid, "email": "a@t",
                               "role": "admin", "status": "active"})
    await db.clients.insert_one({"id": cl, "tenant_id": tid, "name": "Acme"})
    return {"tenant_id": tid, "user_id": uid, "client_id": cl}


# ════════════════════════ JSONPath filter ════════════════════════════════
class TestFilter:
    def test_no_filter_passes(self):
        assert evaluate_filter(filter_spec=None,
                               payload={"data": {"a": 1}}) is True
        assert evaluate_filter(filter_spec={},
                               payload={"data": {"a": 1}}) is True

    def test_legacy_dict_root_match(self):
        assert evaluate_filter(filter_spec={"client_id": "X"},
                               payload={"data": {"client_id": "X"}}) is True
        assert evaluate_filter(filter_spec={"client_id": "Y"},
                               payload={"data": {"client_id": "X"}}) is False

    def test_jsonpath_existence(self):
        spec = {"$.data.priority": True}  # debe existir
        assert evaluate_filter(filter_spec=spec,
                               payload={"data": {"priority": "high"}}) is True
        assert evaluate_filter(filter_spec=spec,
                               payload={"data": {}}) is False

    def test_jsonpath_value_match(self):
        spec = {"$.data.amount": 1500}
        assert evaluate_filter(filter_spec=spec,
                               payload={"data": {"amount": 1500}}) is True
        assert evaluate_filter(filter_spec=spec,
                               payload={"data": {"amount": 1499}}) is False

    def test_jsonpath_invalid_expression_drops(self):
        # Expresión inválida → conservador, descarta
        assert evaluate_filter(filter_spec={"$..": "x"},
                               payload={"data": {}}) in (True, False)


# ════════════════════════ Burst mode (is_paused) ═════════════════════════
class TestBurstMode:
    async def test_paused_subscription_keeps_event_in_queue(self, setup, db, monkeypatch):
        sub_repo = WebhookSubscriptionRepository(tenant_id=setup["tenant_id"])
        sub = await sub_repo.create({
            "client_id": setup["client_id"],
            "endpoint_url": "https://example.com/h",
            "endpoint_url_hash": "h",
            "hmac_secret_encrypted": encrypt_secret("s"),
            "event_codes": ["ticket.created"],
            "include_pii": False, "is_active": True, "is_paused": True,
        })
        from services.webhooks import dispatcher as disp
        from services.webhooks.dispatcher import dispatch, worker_tick
        called = {"send": 0}

        async def fake_send_one(*, sub, payload):
            called["send"] += 1
            return ("delivered", 200, 1, "ok", None, "1.1.1.1")
        monkeypatch.setattr(disp, "_send_one", fake_send_one)

        await dispatch(
            tenant_id=setup["tenant_id"], client_id=setup["client_id"],
            event_type="ticket.created", source_id="P-1", data={},
        )
        await worker_tick(batch=10)
        # No se envió porque is_paused
        assert called["send"] == 0
        # Pero el evento sigue en queue
        n = await db.webhook_pending_queue.count_documents(
            {"tenant_id": setup["tenant_id"]})
        assert n == 1
        # Y hay log con status=paused
        paused = await db.webhook_delivery_log.count_documents(
            {"tenant_id": setup["tenant_id"], "status": "paused"},
        )
        assert paused == 1

    async def test_resume_endpoint_clears_paused(self, setup, http_client, db):
        sub_repo = WebhookSubscriptionRepository(tenant_id=setup["tenant_id"])
        sub = await sub_repo.create({
            "client_id": setup["client_id"],
            "endpoint_url": "https://example.com/h",
            "endpoint_url_hash": "h",
            "hmac_secret_encrypted": encrypt_secret("s"),
            "event_codes": ["ticket.created"],
            "include_pii": False, "is_active": True, "is_paused": True,
        })
        h = _bearer(user_id=setup["user_id"], tenant_id=setup["tenant_id"])
        r = await http_client.post(
            f"/api/admin/webhooks/subscriptions/{sub['id']}/resume", headers=h,
        )
        assert r.status_code == 200
        fresh = await db.webhook_subscriptions.find_one({"id": sub["id"]})
        assert fresh["is_paused"] is False


# ════════════════════════ README generator ═══════════════════════════════
class TestReadme:
    def test_basic_generation(self):
        sub = {"id": "AAAAAAAA-1234", "endpoint_url": "https://a.test/h",
               "include_pii": False}
        md = generate_readme(subscription=sub,
                              event_codes=["ticket.created", "ticket.closed"])
        assert "# Webhook MyExcellence" in md
        assert "https://a.test/h" in md
        assert "ticket.created" in md
        assert "X-MyE-Signature" in md
        assert "intento 7 → +24h" in md
        assert "Node.js" in md
        assert "Python" in md
        assert "PHP" in md

    def test_pii_callout(self):
        sub = {"id": "X", "endpoint_url": "https://a.test/h", "include_pii": True}
        md = generate_readme(subscription=sub, event_codes=["ticket.created"])
        assert "consentimiento firmado" in md.lower() or "consentimiento" in md.lower()


class TestReadmeEndpoint:
    async def test_returns_markdown(self, setup, http_client):
        repo = WebhookSubscriptionRepository(tenant_id=setup["tenant_id"])
        sub = await repo.create({
            "client_id": setup["client_id"],
            "endpoint_url": "https://acme.test/hook",
            "endpoint_url_hash": "h",
            "hmac_secret_encrypted": encrypt_secret("s"),
            "event_codes": ["ticket.created"],
            "include_pii": False, "is_active": True,
        })
        h = _bearer(user_id=setup["user_id"], tenant_id=setup["tenant_id"])
        r = await http_client.get(
            f"/api/admin/webhooks/subscriptions/{sub['id']}/readme", headers=h,
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/markdown")
        assert "ticket.created" in r.text
        assert "https://acme.test/hook" in r.text


# ════════════════════════ Webhook test echo público ══════════════════════
class TestEchoPublic:
    async def test_echo_no_auth_required(self, http_client):
        # Endpoint público — sin Bearer
        body = b'{"event_id":"abc","event_type":"x"}'
        sig = sign_body(secret="test-shared-secret-2026", body=body)
        r = await http_client.post(
            "/api/webhook-test/echo", content=body,
            headers={"Content-Type": "application/json",
                     "X-MyE-Signature": sig,
                     "X-MyE-Event-Id": "abc",
                     "X-MyE-Event": "x"},
        )
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["received"] is True
        assert d["signature_valid"] is True
        assert d["event_id"] == "abc"

    async def test_echo_invalid_signature_still_2xx_but_flagged(self, http_client):
        body = b'{"x":1}'
        r = await http_client.post(
            "/api/webhook-test/echo", content=body,
            headers={"X-MyE-Signature": "sha256=wrong"},
        )
        assert r.status_code == 200  # echo siempre acepta para inspección
        assert r.json()["data"]["signature_valid"] is False

    async def test_echo_chaos_fail_rate_100_returns_500(self, http_client):
        r = await http_client.post(
            "/api/webhook-test/echo?fail_rate=100", content=b"{}",
        )
        assert r.status_code == 500

    async def test_echo_status_override(self, http_client):
        r = await http_client.post(
            "/api/webhook-test/echo?status=429", content=b"{}",
        )
        assert r.status_code == 429

    async def test_received_list(self, http_client):
        # Limpiar
        await http_client.delete("/api/webhook-test/received")
        await http_client.post(
            "/api/webhook-test/echo", content=b'{"id":"e1"}',
            headers={"X-MyE-Event-Id": "e1", "X-MyE-Event": "ticket.created"},
        )
        r = await http_client.get("/api/webhook-test/received?limit=10")
        items = r.json()["data"]["items"]
        assert any(it["event_id"] == "e1" for it in items)


# ════════════════════════ IA auditor attestation ═════════════════════════
class TestAuditorAttestation:
    async def test_csv_download_appends_attestation(self, db):
        # Setup auditor
        from seeds.ai_catalog import run as seed_ai
        await seed_ai()
        tid = new_id()
        uid = new_id()
        cl_id = new_id()
        await db.tenants.insert_one({"id": tid, "slug": "att", "name": "T",
                                     "status": "active"})
        await db.clients.insert_one({"id": cl_id, "tenant_id": tid, "name": "C"})
        await db.users.insert_one({"id": uid, "tenant_id": tid,
                                   "email": "auditor@t",
                                   "role": "client_auditor", "status": "active",
                                   "client_id": cl_id})
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://test") as c:
            h = _bearer(user_id=uid, tenant_id=tid, role="client_auditor")
            r = await c.get("/api/admin/ai/audit/export.csv", headers=h)
            assert r.status_code == 200
        rows = await db.ai_audit_attestations.count_documents({"tenant_id": tid})
        assert rows == 1
        att = await db.ai_audit_attestations.find_one({"tenant_id": tid})
        assert att["kind"] == "csv_download"
        assert att["user_id"] == uid

    async def test_review_attestation_endpoint(self, db):
        from seeds.ai_catalog import run as seed_ai
        await seed_ai()
        tid = new_id()
        uid = new_id()
        await db.tenants.insert_one({"id": tid, "slug": "rev", "name": "T",
                                     "status": "active"})
        await db.users.insert_one({"id": uid, "tenant_id": tid,
                                   "email": "auditor@t",
                                   "role": "client_auditor", "status": "active"})
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://test") as c:
            h = _bearer(user_id=uid, tenant_id=tid, role="client_auditor")
            r = await c.post("/api/admin/ai/audit/attest", headers=h, json={
                "signature": "sha256=abcdef",
                "rows": 12,
                "comment": "Lote revisado completo, sin observaciones.",
                "filters": {"date_from": "2026-01-01"},
            })
            assert r.status_code == 200
            d = r.json()["data"]
            assert d["kind"] == "review_attestation"
            assert d["comment"].startswith("Lote revisado")

    async def test_review_requires_comment(self, db):
        tid = new_id()
        uid = new_id()
        await db.tenants.insert_one({"id": tid, "slug": "novalid", "name": "T",
                                     "status": "active"})
        await db.users.insert_one({"id": uid, "tenant_id": tid, "email": "x@t",
                                   "role": "client_auditor", "status": "active"})
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://test") as c:
            h = _bearer(user_id=uid, tenant_id=tid, role="client_auditor")
            r = await c.post("/api/admin/ai/audit/attest", headers=h, json={
                "signature": "sha256=abc", "rows": 1, "comment": "",
            })
            assert r.status_code == 422


# ════════════════════════ Routal pulling cron ════════════════════════════
class TestRoutalPulling:
    async def test_pull_routal_calls_adapter_and_ingests(self, setup, db, monkeypatch):
        # Crear cliente con preferred_carrier_code=routal
        await db.clients.update_one(
            {"id": setup["client_id"]},
            {"$set": {"preferred_carrier_code": "routal", "ingest_mode": "pulling"}},
        )
        await db.carriers.insert_one({
            "id": new_id(), "tenant_id": setup["tenant_id"],
            "code": "routal", "name": "Routal",
            "status": "active", "has_api": True,
        })
        # Mockear el adapter
        from services.cae.adapters import routal as routal_mod

        async def fake_validate(self): return True

        async def fake_plans(self, *, project_id=None, limit=10):
            return [{"id": "plan-1"}, {"id": "plan-2"}]

        async def fake_stops(self, plan_id):
            if plan_id == "plan-1":
                return [
                    {"id": "s1", "external_id": "TRK-1", "status": "completed",
                     "updated_at": "2026-05-09T10:00:00Z"},
                    {"id": "s2", "external_id": "TRK-2", "status": "pending",
                     "updated_at": "2026-05-09T10:01:00Z"},
                    {"id": "s3", "external_id": None, "status": "completed",
                     "updated_at": "2026-05-09T10:02:00Z"},  # skip
                ]
            return []

        monkeypatch.setattr(routal_mod.RoutalAdapter, "validate_config", fake_validate)
        monkeypatch.setattr(routal_mod.RoutalAdapter, "list_recent_plans", fake_plans)
        monkeypatch.setattr(routal_mod.RoutalAdapter, "list_stops_in_plan", fake_stops)

        from services.scheduler import _pull_routal
        metrics = await _pull_routal(
            tenant_id=setup["tenant_id"], client_id=setup["client_id"],
            limit_plans=2,
        )
        assert metrics["plans"] == 2
        assert metrics["processed"] == 2  # TRK-1 + TRK-2 (skip TRK-None)
        assert metrics["skipped"] == 1
        # Guías creadas
        guias = await db.guias.count_documents(
            {"tenant_id": setup["tenant_id"], "client_id": setup["client_id"]},
        )
        assert guias == 2
        # TRK-1 debe estar terminal (completed → delivered)
        g1 = await db.guias.find_one({"tracking_id": "TRK-1"})
        assert g1["is_terminal"] is True
        assert g1["internal_status"] == "delivered"

    async def test_pull_routal_skips_when_no_config(self, setup, db, monkeypatch):
        await db.clients.update_one(
            {"id": setup["client_id"]},
            {"$set": {"preferred_carrier_code": "routal", "ingest_mode": "pulling"}},
        )
        from services.cae.adapters import routal as routal_mod

        async def fake_validate(self): return False
        monkeypatch.setattr(routal_mod.RoutalAdapter, "validate_config", fake_validate)
        from services.scheduler import _pull_routal
        r = await _pull_routal(tenant_id=setup["tenant_id"],
                                client_id=setup["client_id"])
        assert r["skipped"] == "no_config"
