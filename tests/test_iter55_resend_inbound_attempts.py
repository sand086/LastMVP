"""Iter55 · P3.1 + P3.2 — Resend inbound + delivery_attempts propagation.

Cubre:
  P3.1 Webhook
    - `POST /api/webhooks/resend/inbound` reset counter + log timeline event
    - Match por tag.ticket_id, in_reply_to, subject (tracking)
    - Eventos non-inbound (delivered/bounced) se loggean sin tocar contador
    - Sin secret en env: permite request sin signature
  P3.2 Delivery attempts
    - `bump_attempts_if_event_indicates` con patrones de "intento"
    - Idempotente por (guia, status, event_at)
    - `IngestService` propaga `raw_payload.delivery_attempts` al campo `guia.delivery_attempts`
    - Heurística fallback cuando el adapter no manda el counter
"""
from __future__ import annotations
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.uuid import new_id
from services.delivery_attempts import (
    bump_attempts_if_event_indicates, looks_like_attempt,
)


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def env(db):
    t_id = new_id()
    cli_id = new_id()
    await db.tenants.insert_one(
        {"id": t_id, "slug": "t-55", "name": "T-55", "status": "active"})
    await db.clients.insert_one({
        "id": cli_id, "tenant_id": t_id, "name": "Cli-55", "slug": "cli-55",
    })
    return {"tenant_id": t_id, "client_id": cli_id}


# ─────────────────── P3.1 Resend inbound webhook ───────────────────────
@pytest.mark.asyncio
class TestResendInboundWebhook:
    async def test_inbound_resets_counter_and_logs_event(
            self, db, env, http_client):
        t = env["tenant_id"]
        ticket_id = new_id()
        # Ticket prefix (primeros 8 chars) → como AutomationService envía tag
        ticket_prefix = ticket_id[:8]
        await db.tickets.insert_one({
            "id": ticket_id, "tenant_id": t, "client_id": env["client_id"],
            "status": "waiting_client",
            "client_notifications_count": 3,
            "last_client_notification_at": "2026-05-10T00:00:00+00:00",
            "created_at": "2026-05-10T00:00:00+00:00",
            "updated_at": "2026-05-10T00:00:00+00:00",
        })
        payload = {
            "type": "email.received",
            "data": {
                "from": "responsable@cliente.com",
                "subject": "Re: incidencia",
                "text": "Aquí va el alterno: 555-1234.",
                "tags": {"ticket_id": ticket_prefix},
            },
        }
        r = await http_client.post(
            "/api/webhooks/resend/inbound", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["data"]["action"] == "matched"
        assert body["data"]["ticket_id"] == ticket_id

        # Estado: counter reseteado, status volvió a in_progress
        t_after = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
        assert t_after["client_notifications_count"] == 0
        assert t_after["status"] == "in_progress"
        assert t_after.get("last_client_reply_at")

        # Timeline event creado
        evs = await db.timeline_events.count_documents({
            "ticket_id": ticket_id, "event_type": "client_reply",
        })
        assert evs == 1

    async def test_match_by_subject_tracking(self, db, env, http_client):
        t = env["tenant_id"]
        gid = new_id()
        tid = new_id()
        await db.guias.insert_one({
            "id": gid, "tenant_id": t, "tracking_id": "FX12345678",
        })
        await db.tickets.insert_one({
            "id": tid, "tenant_id": t, "guia_id": gid,
            "status": "waiting_client", "client_notifications_count": 2,
        })
        payload = {
            "type": "email.received",
            "data": {
                "from": "x@y.com",
                "subject": "Re: tracking FX12345678 actualización",
                "text": "Confirmo",
            },
        }
        r = await http_client.post(
            "/api/webhooks/resend/inbound", json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["action"] == "matched"

    async def test_match_by_in_reply_to(self, db, env, http_client):
        t = env["tenant_id"]
        tid = new_id()
        msg_id = "abc-123-msg"
        await db.tickets.insert_one({
            "id": tid, "tenant_id": t, "status": "waiting_client",
            "client_notifications_count": 1,
        })
        await db.email_send_log.insert_one({
            "tenant_id": t, "ticket_id": tid, "message_id": msg_id,
            "created_at": "2026-05-10T00:00:00+00:00",
        })
        payload = {
            "type": "email.received",
            "data": {"from": "y@z.com", "subject": "Re",
                     "in_reply_to": f"<{msg_id}>"},
        }
        r = await http_client.post(
            "/api/webhooks/resend/inbound", json=payload)
        assert r.status_code == 200
        assert r.json()["data"]["action"] == "matched"

    async def test_no_match_returns_no_match(self, db, env, http_client):
        payload = {
            "type": "email.received",
            "data": {"from": "x@y.com", "subject": "random",
                     "tags": {"ticket_id": "nonexist"}},
        }
        r = await http_client.post(
            "/api/webhooks/resend/inbound", json=payload)
        assert r.status_code == 200
        assert r.json()["data"]["action"] == "no_match"

    async def test_non_inbound_events_logged_not_reset(
            self, db, env, http_client):
        t = env["tenant_id"]
        tid = new_id()
        await db.tickets.insert_one({
            "id": tid, "tenant_id": t, "status": "waiting_client",
            "client_notifications_count": 3,
        })
        payload = {
            "type": "email.delivered",
            "data": {"tags": {"ticket_id": tid[:8]}},
        }
        r = await http_client.post(
            "/api/webhooks/resend/inbound", json=payload)
        assert r.status_code == 200
        # NO reset
        after = await db.tickets.find_one({"id": tid}, {"_id": 0})
        assert after["client_notifications_count"] == 3

    async def test_unknown_event_type_ignored(self, http_client):
        r = await http_client.post(
            "/api/webhooks/resend/inbound",
            json={"type": "email.weird.event"})
        assert r.status_code == 200
        assert r.json()["data"]["action"] == "ignored"

    async def test_invalid_json_returns_validation_error(self, http_client):
        r = await http_client.post(
            "/api/webhooks/resend/inbound",
            content=b"{not valid",
            headers={"Content-Type": "application/json"})
        # `fail` con VALIDATION_FAILED → 422 según HTTP_STATUS map
        assert r.status_code == 422


# ─────────────────── P3.2 Delivery attempts ────────────────────────────
class TestLooksLikeAttempt:
    def test_recognized_patterns(self):
        assert looks_like_attempt("Destinatario ausente")
        assert looks_like_attempt("DOMICILIO CERRADO")
        assert looks_like_attempt("Visita realizada")
        assert looks_like_attempt("Intento de entrega 1")

    def test_unrelated_does_not_match(self):
        assert not looks_like_attempt("Entregado")
        assert not looks_like_attempt("En tránsito")
        assert not looks_like_attempt("")
        assert not looks_like_attempt(None)


@pytest.mark.asyncio
class TestBumpAttempts:
    async def test_increments_when_pattern_matches(self, db, env):
        t = env["tenant_id"]
        gid = new_id()
        await db.guias.insert_one({
            "id": gid, "tenant_id": t, "tracking_id": "G1",
            "delivery_attempts": 0,
        })
        n = await bump_attempts_if_event_indicates(
            tenant_id=t, guia_id=gid,
            carrier_status="Destinatario ausente",
            event_at="2026-05-14T10:00:00+00:00",
        )
        assert n == 1
        g = await db.guias.find_one({"id": gid}, {"_id": 0})
        assert g["delivery_attempts"] == 1

    async def test_idempotent_same_event(self, db, env):
        t = env["tenant_id"]
        gid = new_id()
        await db.guias.insert_one({
            "id": gid, "tenant_id": t, "delivery_attempts": 0,
        })
        await bump_attempts_if_event_indicates(
            tenant_id=t, guia_id=gid,
            carrier_status="Domicilio cerrado",
            event_at="2026-05-14T10:00:00+00:00",
        )
        n2 = await bump_attempts_if_event_indicates(
            tenant_id=t, guia_id=gid,
            carrier_status="Domicilio cerrado",
            event_at="2026-05-14T10:00:00+00:00",
        )
        assert n2 is None  # duplicate skip
        g = await db.guias.find_one({"id": gid}, {"_id": 0})
        assert g["delivery_attempts"] == 1

    async def test_different_event_at_increments_separately(self, db, env):
        t = env["tenant_id"]
        gid = new_id()
        await db.guias.insert_one({
            "id": gid, "tenant_id": t, "delivery_attempts": 0,
        })
        await bump_attempts_if_event_indicates(
            tenant_id=t, guia_id=gid,
            carrier_status="Visita",
            event_at="2026-05-14T10:00:00+00:00",
        )
        n2 = await bump_attempts_if_event_indicates(
            tenant_id=t, guia_id=gid,
            carrier_status="Visita",
            event_at="2026-05-15T10:00:00+00:00",
        )
        assert n2 == 2
        g = await db.guias.find_one({"id": gid}, {"_id": 0})
        assert g["delivery_attempts"] == 2

    async def test_non_matching_status_no_op(self, db, env):
        t = env["tenant_id"]
        gid = new_id()
        await db.guias.insert_one({
            "id": gid, "tenant_id": t, "delivery_attempts": 0,
        })
        n = await bump_attempts_if_event_indicates(
            tenant_id=t, guia_id=gid,
            carrier_status="Entregado",
            event_at="2026-05-14T10:00:00+00:00",
        )
        assert n is None


@pytest.mark.asyncio
class TestIngestPropagatesAttempts:
    async def test_adapter_payload_attempts_persisted(self, db, env):
        """Cuando el adapter (FedEx p.ej.) trae `raw_payload.delivery_attempts`,
        IngestService lo guarda en `guia.delivery_attempts`."""
        from services.ingest_service import IngestService
        t = env["tenant_id"]
        svc = IngestService(tenant_id=t)
        await svc.process_event(
            client_id=env["client_id"],
            tracking_id="FX-IT-1",
            carrier_code="fedex",
            carrier_status="En tránsito",
            carrier_status_description="",
            raw_code="IT",
            api_version="v1",
            event_at=datetime.now(timezone.utc).isoformat(),
            raw_payload={"delivery_attempts": 2, "scans_count": 3},
            source="webhook",
        )
        g = await db.guias.find_one({"tracking_id": "FX-IT-1"}, {"_id": 0})
        assert g is not None
        assert g.get("delivery_attempts") == 2

    async def test_heuristic_increments_on_attempt_status(self, db, env):
        """Sin attempts en raw_payload, pero status="Destinatario ausente" →
        heurística incrementa contador."""
        from services.ingest_service import IngestService
        t = env["tenant_id"]
        svc = IngestService(tenant_id=t)
        # 1er evento — crea guía con attempts=0
        await svc.process_event(
            client_id=env["client_id"],
            tracking_id="FX-AB-1",
            carrier_code="fedex",
            carrier_status="En tránsito",
            carrier_status_description="",
            raw_code="IT",
            api_version="v1",
            event_at="2026-05-14T08:00:00+00:00",
            raw_payload={},
            source="webhook",
        )
        # 2do evento — status indica intento
        await svc.process_event(
            client_id=env["client_id"],
            tracking_id="FX-AB-1",
            carrier_code="fedex",
            carrier_status="Destinatario ausente",
            carrier_status_description="",
            raw_code="DEX1",
            api_version="v1",
            event_at="2026-05-14T15:00:00+00:00",
            raw_payload={},  # SIN attempts del adapter
            source="webhook",
        )
        g = await db.guias.find_one({"tracking_id": "FX-AB-1"}, {"_id": 0})
        assert g.get("delivery_attempts") == 1
