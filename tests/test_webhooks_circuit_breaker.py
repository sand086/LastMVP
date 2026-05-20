"""PROMPT 39 V3 P1.1+P1.2 — Tests del circuit breaker por endpoint
   y alerta proactiva por email.
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
    WebhookDeliveryLogRepository, WebhookSubscriptionRepository,
    ensure_webhook_indexes,
)
from seeds.webhook_catalog import run as seed_webhooks
from services.webhooks.circuit_breaker import (
    CB_COOLDOWN_MIN, CB_MIN_SAMPLES, CB_THRESHOLD_PCT,
    compute_failure_rate, evaluate_and_trip, reset_after_success,
)
from services.webhooks.security import encrypt_secret


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
async def sub_setup(db):
    await seed_webhooks()
    await ensure_webhook_indexes()
    tid = new_id()
    uid = new_id()
    cl = new_id()
    await db.tenants.insert_one({"id": tid, "slug": "cb", "name": "T",
                                 "status": "active"})
    await db.users.insert_one({"id": uid, "tenant_id": tid, "email": "admin@t",
                               "role": "admin", "status": "active"})
    await db.clients.insert_one({"id": cl, "tenant_id": tid, "name": "Acme",
                                 "ops_contact_email": "ops@acme.test"})
    sub_repo = WebhookSubscriptionRepository(tenant_id=tid)
    sub = await sub_repo.create({
        "client_id": cl,
        "endpoint_url": "https://example.com/hook",
        "endpoint_url_hash": "h",
        "hmac_secret_encrypted": encrypt_secret("s"),
        "event_codes": ["ticket.created"],
        "include_pii": False, "is_active": True,
    })
    return {"tenant_id": tid, "user_id": uid, "client_id": cl, "sub": sub}


async def _seed_attempts(db, *, tenant_id, subscription_id,
                          successes=0, failures=0, status="failed_temporary"):
    """Inyecta entradas en el delivery log."""
    repo = WebhookDeliveryLogRepository(tenant_id=tenant_id)
    for _ in range(successes):
        await repo.append({
            "subscription_id": subscription_id, "event_id": new_id(),
            "event_code": "ticket.created", "schema_version": "v1",
            "attempt_number": 1, "status": "delivered",
            "http_status_code": 200, "latency_ms": 10,
            "payload_hash": "h", "payload_size_bytes": 1,
            "endpoint_url_hash": "h", "pii_masked": False,
        })
    for _ in range(failures):
        await repo.append({
            "subscription_id": subscription_id, "event_id": new_id(),
            "event_code": "ticket.created", "schema_version": "v1",
            "attempt_number": 1, "status": status,
            "http_status_code": 503 if status != "timeout" else None,
            "latency_ms": 9, "payload_hash": "h", "payload_size_bytes": 1,
            "endpoint_url_hash": "h", "pii_masked": False,
            "error_message": "boom",
        })


# ════════════════════════ compute_failure_rate ═══════════════════════════
class TestFailureRate:
    async def test_no_attempts_returns_zero(self, sub_setup, db):
        m = await compute_failure_rate(
            tenant_id=sub_setup["tenant_id"],
            subscription_id=sub_setup["sub"]["id"],
        )
        assert m["total_attempts"] == 0
        assert m["rate_pct"] == 0

    async def test_50_50_returns_50pct(self, sub_setup, db):
        await _seed_attempts(db, tenant_id=sub_setup["tenant_id"],
                              subscription_id=sub_setup["sub"]["id"],
                              successes=2, failures=2)
        m = await compute_failure_rate(
            tenant_id=sub_setup["tenant_id"],
            subscription_id=sub_setup["sub"]["id"],
        )
        assert m["total_attempts"] == 4
        assert m["failures"] == 2
        assert m["rate_pct"] == 50.0


# ════════════════════════ evaluate_and_trip ══════════════════════════════
class TestEvaluateAndTrip:
    async def test_below_min_samples_does_not_trip(self, sub_setup, db):
        # 4 fallas (<5 mínimo) — no debe abrir
        await _seed_attempts(db, tenant_id=sub_setup["tenant_id"],
                              subscription_id=sub_setup["sub"]["id"],
                              failures=4)
        r = await evaluate_and_trip(
            tenant_id=sub_setup["tenant_id"],
            subscription_id=sub_setup["sub"]["id"],
        )
        assert r is None

    async def test_below_threshold_does_not_trip(self, sub_setup, db):
        # 8 sucesos + 2 fallos = 20% < 30%
        await _seed_attempts(db, tenant_id=sub_setup["tenant_id"],
                              subscription_id=sub_setup["sub"]["id"],
                              successes=8, failures=2)
        r = await evaluate_and_trip(
            tenant_id=sub_setup["tenant_id"],
            subscription_id=sub_setup["sub"]["id"],
        )
        assert r is None

    async def test_above_threshold_trips(self, sub_setup, db):
        # 1 éxito + 5 fallos = ~83%
        await _seed_attempts(db, tenant_id=sub_setup["tenant_id"],
                              subscription_id=sub_setup["sub"]["id"],
                              successes=1, failures=5)
        # Stub email para no I/O en test
        with patch("services.notification_service.send_email",
                   create=True) as _m:
            from services.notification_service import EmailResult
            _m.return_value = EmailResult(ok=True, id="mock", mock=True)
            r = await evaluate_and_trip(
                tenant_id=sub_setup["tenant_id"],
                subscription_id=sub_setup["sub"]["id"],
            )
        assert r is not None and r["tripped"] is True
        # Sub queda marcada
        sub = await db.webhook_subscriptions.find_one(
            {"id": sub_setup["sub"]["id"]}, {"_id": 0},
        )
        assert sub["is_circuit_open"] is True
        assert sub["circuit_open_until"] > datetime.now(timezone.utc).isoformat()

    async def test_already_open_in_cooldown_does_not_re_trip(self, sub_setup, db):
        # Pre-abrir manualmente con cooldown vigente
        future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        await db.webhook_subscriptions.update_one(
            {"id": sub_setup["sub"]["id"]},
            {"$set": {"is_circuit_open": True, "circuit_open_until": future}},
        )
        await _seed_attempts(db, tenant_id=sub_setup["tenant_id"],
                              subscription_id=sub_setup["sub"]["id"],
                              failures=10)
        r = await evaluate_and_trip(
            tenant_id=sub_setup["tenant_id"],
            subscription_id=sub_setup["sub"]["id"],
        )
        assert r is None  # idempotente


# ════════════════════════ reset_after_success ════════════════════════════
class TestResetAfterSuccess:
    async def test_no_op_when_circuit_not_open(self, sub_setup, db):
        r = await reset_after_success(
            tenant_id=sub_setup["tenant_id"],
            subscription_id=sub_setup["sub"]["id"],
        )
        assert r is None

    async def test_does_not_close_during_cooldown(self, sub_setup, db):
        future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        await db.webhook_subscriptions.update_one(
            {"id": sub_setup["sub"]["id"]},
            {"$set": {"is_circuit_open": True, "circuit_open_until": future}},
        )
        r = await reset_after_success(
            tenant_id=sub_setup["tenant_id"],
            subscription_id=sub_setup["sub"]["id"],
        )
        assert r is None

    async def test_closes_after_cooldown_expires(self, sub_setup, db):
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        await db.webhook_subscriptions.update_one(
            {"id": sub_setup["sub"]["id"]},
            {"$set": {"is_circuit_open": True, "circuit_open_until": past}},
        )
        r = await reset_after_success(
            tenant_id=sub_setup["tenant_id"],
            subscription_id=sub_setup["sub"]["id"],
        )
        assert r == {"closed": True}
        sub = await db.webhook_subscriptions.find_one(
            {"id": sub_setup["sub"]["id"]}, {"_id": 0},
        )
        assert sub["is_circuit_open"] is False


# ════════════════════════ Endpoint reset-circuit ═════════════════════════
class TestResetCircuitEndpoint:
    async def test_admin_can_force_close(self, sub_setup, http_client, db):
        # Estado abierto
        future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        await db.webhook_subscriptions.update_one(
            {"id": sub_setup["sub"]["id"]},
            {"$set": {"is_circuit_open": True, "circuit_open_until": future}},
        )
        h = _bearer(user_id=sub_setup["user_id"],
                    tenant_id=sub_setup["tenant_id"], role="admin")
        r = await http_client.post(
            f"/api/admin/webhooks/subscriptions/{sub_setup['sub']['id']}/reset-circuit",
            headers=h,
        )
        assert r.status_code == 200
        sub = await db.webhook_subscriptions.find_one(
            {"id": sub_setup["sub"]["id"]}, {"_id": 0},
        )
        assert sub["is_circuit_open"] is False
        assert sub["circuit_manually_reset_by"] == sub_setup["user_id"]


# ════════════════════════ Health expone CB metrics ═══════════════════════
class TestHealthCircuitMetrics:
    async def test_health_includes_circuit_metrics_1h(self, sub_setup,
                                                       http_client, db):
        await _seed_attempts(db, tenant_id=sub_setup["tenant_id"],
                              subscription_id=sub_setup["sub"]["id"],
                              successes=2, failures=1)
        h = _bearer(user_id=sub_setup["user_id"],
                    tenant_id=sub_setup["tenant_id"], role="admin")
        r = await http_client.get(
            f"/api/admin/webhooks/subscriptions/{sub_setup['sub']['id']}/health",
            headers=h,
        )
        assert r.status_code == 200
        d = r.json()["data"]
        assert "circuit_metrics_1h" in d
        assert d["circuit_metrics_1h"]["total_attempts"] >= 3


# ════════════════════════ Email recipient resolution ═════════════════════
class TestEmailRecipient:
    async def test_uses_ops_contact_email_first(self, sub_setup, db):
        # Forzar trip con email mockeado y capturar destinatario
        await _seed_attempts(db, tenant_id=sub_setup["tenant_id"],
                              subscription_id=sub_setup["sub"]["id"],
                              successes=0, failures=6)
        captured: dict = {}

        async def fake_send(**kwargs):
            captured.update(kwargs)
            from services.notification_service import EmailResult
            return EmailResult(ok=True, id="m", mock=True)

        with patch("services.notification_service.send_email", new=fake_send):
            r = await evaluate_and_trip(
                tenant_id=sub_setup["tenant_id"],
                subscription_id=sub_setup["sub"]["id"],
            )
        assert r["tripped"] is True
        assert captured.get("to") == "ops@acme.test"
        assert "Webhook caído" in captured.get("subject", "")

    async def test_fallback_to_admin_when_no_ops_email(self, sub_setup, db):
        # Quitar ops_contact_email del cliente
        await db.clients.update_one(
            {"id": sub_setup["client_id"]},
            {"$set": {"ops_contact_email": None}},
        )
        await _seed_attempts(db, tenant_id=sub_setup["tenant_id"],
                              subscription_id=sub_setup["sub"]["id"],
                              successes=0, failures=6)
        captured: dict = {}

        async def fake_send(**kwargs):
            captured.update(kwargs)
            from services.notification_service import EmailResult
            return EmailResult(ok=True, id="m", mock=True)

        with patch("services.notification_service.send_email", new=fake_send):
            await evaluate_and_trip(
                tenant_id=sub_setup["tenant_id"],
                subscription_id=sub_setup["sub"]["id"],
            )
        # El fallback es el admin del tenant
        assert captured.get("to") == "admin@t"


# ════════════════════════ Constantes ═════════════════════════════════════
class TestConfig:
    def test_defaults_match_prompt_spec(self):
        # PROMPT 39 V3 P1.1: 30% en 1h, mínimo 5 samples, cooldown 5min
        assert CB_THRESHOLD_PCT == 30
        assert CB_MIN_SAMPLES == 5
        assert CB_COOLDOWN_MIN == 5
