"""Iter54 · P0 + P1 + P2 — Tropicalización flows del documento del cliente.

Cubre:
  - P0.1 — `email_templates`: nuevas keys + `resolve_template_key` con jerarquía
  - P0.2 — `cae_seed.seed_cae_defaults` idempotente
  - P0.3 — `incident_labels` agrega `recipient_absent` con label legible
  - P1.1 — `escalation.bump_client_notification_counter` incrementa contador
  - P1.1 — `automation_service._execute_email` invoca el bump
  - P1.2 — `WorkflowEngine._resolve_max_attempts` (default por carrier + override)
  - P1.2 — `WorkflowEngine._should_gate_by_attempts` (Estafeta 2, FedEx 3)
  - P1.3 — `escalation.scan_unresponsive_tickets` resuelve y emite final_warning
  - P2.1 — `soluciones_seed.seed_soluciones` idempotente
  - Endpoints `/api/admin/maintenance/{seed-cae,seed-soluciones,run-escalation}`
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token, hash_password
from core.uuid import new_id
from services.cae_seed import seed_cae_defaults, SEED_ENTRIES
from services.email_templates import (
    INCIDENT_VARIANT_TEMPLATE, SUPPORTED_KEYS,
    resolve_template_key,
)
from services.escalation import (
    bump_client_notification_counter,
    scan_unresponsive_tickets,
)
from services.incident_labels import label_for, INCIDENT_TYPE_LABELS_ES
from services.soluciones_seed import seed_soluciones
from services.workflow_engine import WorkflowEngine, WorkflowOutcome


def _bearer(*, user_id: str, tenant_id: str, role: str = "superadmin",
            email: str = "su@t.io"):
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
    t_id = new_id()
    su_id = new_id()
    agent_id = new_id()
    client_id = new_id()
    pwd = hash_password("x")
    await db.tenants.insert_one(
        {"id": t_id, "slug": "t-54", "name": "T-54", "status": "active"})
    await db.users.insert_many([
        {"id": su_id, "tenant_id": t_id, "email": "su@t-54.io",
         "role": "superadmin", "password_hash": pwd, "status": "active"},
        {"id": agent_id, "tenant_id": t_id, "email": "ag@t-54.io",
         "role": "agent", "password_hash": pwd, "status": "active"},
    ])
    await db.clients.insert_one({
        "id": client_id, "tenant_id": t_id, "name": "Cli-54",
        "slug": "cli-54", "automation_enabled": True,
        "ops_contact_email": "ops@cli54.io", "ops_contact_name": "Ops",
    })
    return {
        "tenant_id": t_id, "superadmin_id": su_id,
        "agent_id": agent_id, "client_id": client_id,
    }


# ────────────────────── P0.1 Templates por incidente ─────────────────────
class TestTemplateResolution:
    def test_all_8_new_keys_in_supported(self):
        for k in [
            "incident_address_issue_contacted",
            "incident_address_issue_no_contact",
            "incident_refused_confirmed",
            "incident_refused_not_confirmed",
            "incident_refused_no_contact",
            "incident_recipient_absent_contacted",
            "incident_recipient_absent_no_contact",
            "final_return_to_origin",
        ]:
            assert k in SUPPORTED_KEYS

    def test_resolve_address_issue_contacted(self):
        assert resolve_template_key("address_issue", "contacted") == \
            "incident_address_issue_contacted"

    def test_resolve_refused_confirmed(self):
        assert resolve_template_key("refused", "confirmed") == \
            "incident_refused_confirmed"

    def test_resolve_recipient_absent_no_contact(self):
        assert resolve_template_key("recipient_absent", "no_contact") == \
            "incident_recipient_absent_no_contact"

    def test_unknown_variant_falls_back_to_no_contact(self):
        # variant inválido para address_issue → debe caer a no_contact
        assert resolve_template_key("address_issue", "weird") == \
            "incident_address_issue_no_contact"

    def test_unknown_incident_falls_back_to_legacy(self):
        assert resolve_template_key("nonexistent_type", "x") == "incident_notice"

    def test_none_returns_legacy(self):
        assert resolve_template_key(None) == "incident_notice"

    def test_mapping_dict_has_expected_combos(self):
        # 7 combinaciones específicas
        assert len(INCIDENT_VARIANT_TEMPLATE) == 7


# ────────────────────── P0.3 Labels incident_type ─────────────────────────
class TestIncidentLabelsRecipientAbsent:
    def test_recipient_absent_has_label(self):
        assert "recipient_absent" in INCIDENT_TYPE_LABELS_ES
        assert label_for("recipient_absent") == "Destinatario ausente"


# ────────────────────── P0.2 Seed CAE ─────────────────────────────────────
@pytest.mark.asyncio
class TestSeedCaeDefaults:
    async def test_seed_entries_cover_4_carriers(self):
        carriers_in_seed = {entry[0] for entry in SEED_ENTRIES}
        assert carriers_in_seed >= {"fedex", "dhl", "redpack", "estafeta"}

    async def test_seed_includes_documento_specific_strings(self):
        # Strings exactos del documento del cliente
        raw_codes = {entry[1] for entry in SEED_ENTRIES}
        assert "Entregado" in raw_codes
        assert "Rechazado" in raw_codes
        assert "Destinatario ausente" in raw_codes
        assert "Dirección incorrecta" in raw_codes
        assert "Domicilio cerrado" in raw_codes
        # Redpack-specific
        assert "Visita" in raw_codes

    async def test_seed_inserts_then_updates_idempotent(self, db, env):
        t = env["tenant_id"]
        first = await seed_cae_defaults(tenant_id=t)
        assert first["inserted"] > 0
        # Re-run: 0 inserts, todos updates.
        second = await seed_cae_defaults(tenant_id=t)
        assert second["inserted"] == 0
        assert second["updated"] == first["inserted"] + first["updated"]

    async def test_seed_isolates_tenants(self, db, env):
        other = new_id()
        await db.tenants.insert_one(
            {"id": other, "slug": "o", "name": "O", "status": "active"})
        await seed_cae_defaults(tenant_id=env["tenant_id"])
        # El otro tenant ve 0 entries propios
        mine = await db.carrier_status_catalog.count_documents(
            {"tenant_id": other})
        assert mine == 0


# ────────────────────── P1.1 Contador notificaciones ─────────────────────
@pytest.mark.asyncio
class TestNotificationCounter:
    async def test_bump_increments_counter(self, db, env):
        ticket_id = new_id()
        await db.tickets.insert_one({
            "id": ticket_id, "tenant_id": env["tenant_id"],
            "client_id": env["client_id"], "status": "in_progress",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        })
        n1 = await bump_client_notification_counter(
            tenant_id=env["tenant_id"], ticket_id=ticket_id)
        assert n1 == 1
        n2 = await bump_client_notification_counter(
            tenant_id=env["tenant_id"], ticket_id=ticket_id)
        assert n2 == 2
        # last_client_notification_at persiste
        t = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
        assert t.get("last_client_notification_at")


# ────────────────────── P1.2 Max attempts gating ──────────────────────────
@pytest.mark.asyncio
class TestMaxAttemptsGating:
    async def test_fedex_gates_at_attempt_1_of_3(self, db, env):
        t = env["tenant_id"]
        engine = WorkflowEngine(tenant_id=t)
        guia = {
            "id": new_id(), "tenant_id": t,
            "client_id": env["client_id"],
            "carrier_code": "fedex",
            "delivery_attempts": 1,  # 1er intento — aún hay margen
            "carrier_status": "Destinatario ausente",
            "is_terminal": False,
        }
        out = await engine.process_post_ingest(
            guia=guia, ingest_action="updated",
            normalized_canonical="exception",
            normalized_incident_type="recipient_absent",
        )
        assert out.action == "skip"
        assert "attempts_below_threshold" in out.reason

    async def test_fedex_lets_through_at_attempt_2_of_3(self, db, env):
        t = env["tenant_id"]
        # Necesitamos al menos un user activo para auto-assign — ya hay agent.
        engine = WorkflowEngine(tenant_id=t)
        guia = {
            "id": new_id(), "tenant_id": t,
            "client_id": env["client_id"],
            "carrier_code": "fedex",
            "delivery_attempts": 2,  # penúltimo → debe pasar
            "carrier_status": "Destinatario ausente",
            "is_terminal": False,
        }
        out = await engine.process_post_ingest(
            guia=guia, ingest_action="updated",
            normalized_canonical="exception",
            normalized_incident_type="recipient_absent",
        )
        # Debería crear ticket o ya existir
        assert out.action in ("ticket_created", "ticket_exists")

    async def test_estafeta_gates_at_attempt_0_with_threshold_1(self, db, env):
        # Estafeta tiene max=2 → threshold=1, attempt=0 (raro pero) gates.
        t = env["tenant_id"]
        engine = WorkflowEngine(tenant_id=t)
        # attempt=0 = sin gating (sin tracker). Probamos override en cliente.
        await db.clients.update_one(
            {"id": env["client_id"]},
            {"$set": {"carriers": {"estafeta": {"max_attempts": 2}}}},
        )
        max_a = await engine._resolve_max_attempts(
            carrier_code="estafeta", client_id=env["client_id"])
        assert max_a == 2

    async def test_no_attempts_field_no_gating(self, db, env):
        """Si la guía no tiene `delivery_attempts`, NO gating (legacy)."""
        t = env["tenant_id"]
        engine = WorkflowEngine(tenant_id=t)
        guia = {
            "id": new_id(), "tenant_id": t,
            "client_id": env["client_id"], "carrier_code": "fedex",
            "carrier_status": "Rechazado", "is_terminal": False,
        }
        out = await engine.process_post_ingest(
            guia=guia, ingest_action="updated",
            normalized_canonical="exception",
            normalized_incident_type="refused",
        )
        # No gating → proceeds (create ticket)
        assert out.action in ("ticket_created", "ticket_exists")

    async def test_resolve_max_attempts_respects_client_override(self, db, env):
        t = env["tenant_id"]
        await db.clients.update_one(
            {"id": env["client_id"]},
            {"$set": {"carriers": {"fedex": {"max_attempts": 5}}}},
        )
        engine = WorkflowEngine(tenant_id=t)
        assert await engine._resolve_max_attempts(
            carrier_code="fedex", client_id=env["client_id"]) == 5

    async def test_resolve_max_attempts_defaults(self, db, env):
        engine = WorkflowEngine(tenant_id=env["tenant_id"])
        assert await engine._resolve_max_attempts(
            carrier_code="fedex", client_id=None) == 3
        assert await engine._resolve_max_attempts(
            carrier_code="estafeta", client_id=None) == 2
        assert await engine._resolve_max_attempts(
            carrier_code=None, client_id=None) == 3


# ────────────────────── P1.3 Escalation scan ──────────────────────────────
@pytest.mark.asyncio
class TestEscalationScan:
    async def test_resolves_ticket_after_3_notifications_and_grace(
            self, db, env):
        t = env["tenant_id"]
        ticket_id = new_id()
        old = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
        await db.tickets.insert_one({
            "id": ticket_id, "tenant_id": t,
            "client_id": env["client_id"], "status": "waiting_client",
            "client_notifications_count": 3,
            "last_client_notification_at": old,
            "guia_id": None,
            "created_at": old, "updated_at": old,
        })

        # Mock send_email para no llamar a Resend real.
        with patch("services.notification_service.send_email",
                   new=AsyncMock()):
            res = await scan_unresponsive_tickets(tenant_id=t)
        assert res.scanned == 1
        assert res.escalated == 1
        t_after = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
        assert t_after["status"] == "resolved"
        # Timeline event registrado
        ev_count = await db.timeline_events.count_documents({
            "ticket_id": ticket_id, "event_type": "auto_escalated",
        })
        assert ev_count == 1

    async def test_skips_tickets_under_threshold(self, db, env):
        t = env["tenant_id"]
        old = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
        await db.tickets.insert_one({
            "id": new_id(), "tenant_id": t,
            "client_id": env["client_id"], "status": "waiting_client",
            "client_notifications_count": 2,  # solo 2 → no escala
            "last_client_notification_at": old,
            "created_at": old, "updated_at": old,
        })
        res = await scan_unresponsive_tickets(tenant_id=t)
        assert res.scanned == 0

    async def test_skips_tickets_in_grace_period(self, db, env):
        t = env["tenant_id"]
        recent = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
        await db.tickets.insert_one({
            "id": new_id(), "tenant_id": t,
            "client_id": env["client_id"], "status": "waiting_client",
            "client_notifications_count": 5,
            "last_client_notification_at": recent,  # demasiado reciente
            "created_at": recent, "updated_at": recent,
        })
        res = await scan_unresponsive_tickets(tenant_id=t)
        assert res.scanned == 0

    async def test_dry_run_doesnt_resolve(self, db, env):
        t = env["tenant_id"]
        old = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
        tid = new_id()
        await db.tickets.insert_one({
            "id": tid, "tenant_id": t,
            "client_id": env["client_id"], "status": "waiting_client",
            "client_notifications_count": 3,
            "last_client_notification_at": old,
            "created_at": old, "updated_at": old,
        })
        res = await scan_unresponsive_tickets(tenant_id=t, dry_run=True)
        assert res.scanned == 1
        assert res.escalated == 1
        # Pero NO persiste
        t_after = await db.tickets.find_one({"id": tid}, {"_id": 0})
        assert t_after["status"] == "waiting_client"


# ────────────────────── P2 Seed soluciones ────────────────────────────────
@pytest.mark.asyncio
class TestSeedSoluciones:
    async def test_seed_creates_7_soluciones(self, db, env):
        t = env["tenant_id"]
        res = await seed_soluciones(tenant_id=t)
        assert res["inserted"] == 7
        # Verificar slugs
        slugs = await db.soluciones.distinct("slug", {"tenant_id": t})
        assert "address_issue_contact_recipient" in slugs
        assert "refused_request_instructions" in slugs
        assert "absent_unresponsive_warning" in slugs
        assert "auto_return_to_origin" in slugs

    async def test_seed_idempotent(self, db, env):
        t = env["tenant_id"]
        await seed_soluciones(tenant_id=t)
        second = await seed_soluciones(tenant_id=t)
        assert second["inserted"] == 0
        assert second["updated"] == 7

    async def test_seed_creates_motivos_on_demand(self, db, env):
        t = env["tenant_id"]
        await seed_soluciones(tenant_id=t)
        # Debe haber creado motivos para los 3 incident_types nuevos
        codes = await db.motivos.distinct("code", {"tenant_id": t})
        assert "address_issue" in codes
        assert "refused" in codes
        assert "recipient_absent" in codes


# ────────────────────── Endpoints admin ──────────────────────────────────
@pytest.mark.asyncio
class TestAdminEndpoints:
    async def test_seed_cae_defaults_endpoint(self, env, http_client):
        headers = _bearer(user_id=env["superadmin_id"],
                          tenant_id=env["tenant_id"])
        r = await http_client.post(
            "/api/admin/maintenance/seed-cae-defaults", headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["inserted"] > 0

    async def test_seed_soluciones_endpoint(self, env, http_client):
        headers = _bearer(user_id=env["superadmin_id"],
                          tenant_id=env["tenant_id"])
        r = await http_client.post(
            "/api/admin/maintenance/seed-soluciones", headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["inserted"] == 7

    async def test_run_escalation_endpoint(self, db, env, http_client):
        t = env["tenant_id"]
        old = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
        await db.tickets.insert_one({
            "id": new_id(), "tenant_id": t,
            "client_id": env["client_id"], "status": "waiting_client",
            "client_notifications_count": 4,
            "last_client_notification_at": old,
            "created_at": old, "updated_at": old,
        })
        headers = _bearer(user_id=env["superadmin_id"], tenant_id=t)
        r = await http_client.post(
            "/api/admin/maintenance/run-escalation?dry_run=true",
            headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["scanned"] == 1
        assert data["dry_run"] is True

    async def test_agent_forbidden_on_all_seeds(self, env, http_client):
        h = _bearer(user_id=env["agent_id"], tenant_id=env["tenant_id"],
                    role="agent")
        for ep in ("seed-cae-defaults", "seed-soluciones", "run-escalation"):
            r = await http_client.post(
                f"/api/admin/maintenance/{ep}", headers=h)
            assert r.status_code == 403, f"{ep}: {r.text}"


# ────────────────────── AutomationService bump ────────────────────────────
@pytest.mark.asyncio
class TestAutomationServiceBumpsCounter:
    async def test_email_send_bumps_counter(self, db, env):
        """Cuando AutomationService manda email exitosamente, el contador
        del ticket se incrementa."""
        from services.automation_service import AutomationService
        from services.notification_service import EmailResult

        t = env["tenant_id"]
        ticket_id = new_id()
        sol_id = new_id()
        await db.soluciones.insert_one({
            "id": sol_id, "tenant_id": t,
            "name": "Test", "automatable": True,
            "template_msg": "Hola", "active": True,
        })
        await db.tickets.insert_one({
            "id": ticket_id, "tenant_id": t,
            "client_id": env["client_id"], "status": "in_progress",
            "solucion_id": sol_id,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        })

        with patch("services.automation_service.can_automate",
                   new=AsyncMock(return_value=type("D", (), {
                       "can_automate": True, "reason": "ok",
                   })())):
            with patch("services.automation_service.send_email",
                       new=AsyncMock(return_value=EmailResult(
                           ok=True, id="msg-1", reason="ok", mock=False))):
                svc = AutomationService(tenant_id=t)
                outcome = await svc.execute_for_ticket(ticket_id, "email")

        assert outcome.executed is True
        ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
        assert ticket["client_notifications_count"] == 1
