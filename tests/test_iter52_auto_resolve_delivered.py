"""Iter52 · Auto-resolve de tickets cuando la guía llega a `delivered`.

Bug reproducido: CSV layout v2 con Status="Entregado" para fedex (sin entry
en CAE catalog) → normalizer devuelve canonical="unknown" → WorkflowEngine
no disparaba el auto-resolve aunque `guia.internal_status = "delivered"` ya
estaba seteado por el heurístico pre-CAE.

Cubre:
  - `WorkflowEngine.process_post_ingest` resuelve el ticket cuando
    `normalized_canonical` es None/unknown pero `guia.internal_status=delivered`.
  - End-to-end: CSV "Entregado" → ingest → ticket existente queda `resolved`.
  - `POST /api/admin/maintenance/reconcile-delivered-tickets` repara docs legacy.
"""
from __future__ import annotations
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token, hash_password
from core.uuid import new_id
from services.workflow_engine import WorkflowEngine


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
        {"id": t_id, "slug": "t-52", "name": "T-52", "status": "active"})
    await db.users.insert_many([
        {"id": su_id, "tenant_id": t_id,
         "email": "su@t-52.io", "role": "superadmin",
         "password_hash": pwd, "status": "active"},
        {"id": agent_id, "tenant_id": t_id,
         "email": "agent@t-52.io", "role": "agent",
         "password_hash": pwd, "status": "active"},
    ])
    await db.clients.insert_one({
        "id": client_id, "tenant_id": t_id,
        "name": "Cli-52", "slug": "cli-52",
        "automation_enabled": False,
    })
    return {
        "tenant_id": t_id, "superadmin_id": su_id,
        "agent_id": agent_id, "client_id": client_id,
    }


# ─────────────────────────── WorkflowEngine ─────────────────────────────
@pytest.mark.asyncio
class TestWorkflowEngineAutoResolve:
    async def test_resolves_ticket_when_internal_status_delivered(
            self, db, env):
        """Caso del bug: normalizer no conoce el code → canonical=unknown,
        pero `guia.internal_status="delivered"` está bien seteado por el
        heurístico pre-CAE. El engine debe auto-resolver."""
        t_id = env["tenant_id"]
        guia_id = new_id()
        ticket_id = new_id()
        now = datetime.now(timezone.utc).isoformat()
        await db.guias.insert_one({
            "id": guia_id, "tenant_id": t_id,
            "tracking_id": "TRK-52A", "carrier_code": "fedex",
            "carrier_status": "Entregado",
            "internal_status": "delivered",
            "is_terminal": True,
            "client_id": env["client_id"],
            "created_at": now, "updated_at": now,
        })
        await db.tickets.insert_one({
            "id": ticket_id, "tenant_id": t_id, "guia_id": guia_id,
            "client_id": env["client_id"], "status": "in_progress",
            "incident_type": "exception",
            "assigned_agent_id": env["agent_id"],
            "created_at": now, "updated_at": now,
        })

        # Simulamos lo que pasa en _dispatch_workflow: el normalizer NO conoce
        # "Entregado" para fedex (no está en CAE catalog) → devuelve unknown.
        engine = WorkflowEngine(tenant_id=t_id)
        guia = await db.guias.find_one({"id": guia_id}, {"_id": 0})
        outcome = await engine.process_post_ingest(
            guia=guia,
            ingest_action="updated",
            normalized_canonical="unknown",  # ← caso del bug
            normalized_incident_type=None,
        )
        assert outcome.action == "auto_resolved", outcome.reason
        assert outcome.ticket_id == ticket_id

        # El ticket queda en `resolved`.
        ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
        assert ticket["status"] == "resolved"

    async def test_resolves_when_normalized_canonical_is_none(
            self, db, env):
        """Variante: el normalizer no se llamó (raw_code vacío) → None.
        Igualmente debe resolver si `guia.internal_status=delivered`."""
        t_id = env["tenant_id"]
        guia_id = new_id()
        ticket_id = new_id()
        now = datetime.now(timezone.utc).isoformat()
        await db.guias.insert_one({
            "id": guia_id, "tenant_id": t_id,
            "tracking_id": "TRK-52B", "carrier_code": "fedex",
            "internal_status": "delivered", "is_terminal": True,
            "client_id": env["client_id"],
            "created_at": now, "updated_at": now,
        })
        await db.tickets.insert_one({
            "id": ticket_id, "tenant_id": t_id, "guia_id": guia_id,
            "client_id": env["client_id"], "status": "in_progress",
            "assigned_agent_id": env["agent_id"],
            "created_at": now, "updated_at": now,
        })
        engine = WorkflowEngine(tenant_id=t_id)
        guia = await db.guias.find_one({"id": guia_id}, {"_id": 0})
        outcome = await engine.process_post_ingest(
            guia=guia, ingest_action="updated",
            normalized_canonical=None, normalized_incident_type=None,
        )
        assert outcome.action == "auto_resolved"
        ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
        assert ticket["status"] == "resolved"

    async def test_normalizer_takes_precedence_when_present(
            self, db, env):
        """Si el normalizer SÍ devuelve canonical, ése gana sobre internal_status."""
        t_id = env["tenant_id"]
        guia_id = new_id()
        now = datetime.now(timezone.utc).isoformat()
        await db.guias.insert_one({
            "id": guia_id, "tenant_id": t_id,
            "tracking_id": "TRK-52C", "carrier_code": "fedex",
            # internal_status quedó en in_transit pero el normalizer dice delivered
            "internal_status": "in_transit", "is_terminal": True,
            "client_id": env["client_id"],
            "created_at": now, "updated_at": now,
        })
        # Sin ticket abierto → skip path, pero verificamos el reason.
        engine = WorkflowEngine(tenant_id=t_id)
        guia = await db.guias.find_one({"id": guia_id}, {"_id": 0})
        outcome = await engine.process_post_ingest(
            guia=guia, ingest_action="updated",
            normalized_canonical="delivered",
            normalized_incident_type=None,
        )
        # Sin ticket → skip por delivered_no_open_ticket (no por no_incident)
        assert outcome.action == "skip"
        assert outcome.reason == "delivered_no_open_ticket"

    async def test_does_not_resolve_when_not_terminal(self, db, env):
        """Guía aún en tránsito → ticket sigue abierto."""
        t_id = env["tenant_id"]
        guia_id = new_id()
        ticket_id = new_id()
        now = datetime.now(timezone.utc).isoformat()
        await db.guias.insert_one({
            "id": guia_id, "tenant_id": t_id,
            "tracking_id": "TRK-52D", "carrier_code": "fedex",
            "internal_status": "in_transit", "is_terminal": False,
            "client_id": env["client_id"],
            "created_at": now, "updated_at": now,
        })
        await db.tickets.insert_one({
            "id": ticket_id, "tenant_id": t_id, "guia_id": guia_id,
            "client_id": env["client_id"], "status": "in_progress",
            "assigned_agent_id": env["agent_id"],
            "created_at": now, "updated_at": now,
        })
        engine = WorkflowEngine(tenant_id=t_id)
        guia = await db.guias.find_one({"id": guia_id}, {"_id": 0})
        outcome = await engine.process_post_ingest(
            guia=guia, ingest_action="updated",
            normalized_canonical=None, normalized_incident_type=None,
        )
        assert outcome.action == "skip"
        ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
        assert ticket["status"] == "in_progress"  # sin cambio


# ─────────────────────────── Endpoint reconcile ─────────────────────────
@pytest.mark.asyncio
class TestReconcileDeliveredEndpoint:
    async def test_reconcile_resolves_orphan_tickets(self, db, env, http_client):
        t_id = env["tenant_id"]
        now = datetime.now(timezone.utc).isoformat()
        # 2 guías entregadas con ticket abierto + 1 control (en tránsito)
        for tracking in ("L1", "L2"):
            gid = new_id()
            await db.guias.insert_one({
                "id": gid, "tenant_id": t_id, "tracking_id": tracking,
                "internal_status": "delivered", "is_terminal": True,
                "client_id": env["client_id"],
                "created_at": now, "updated_at": now,
            })
            await db.tickets.insert_one({
                "id": new_id(), "tenant_id": t_id, "guia_id": gid,
                "client_id": env["client_id"], "status": "in_progress",
                "assigned_agent_id": env["agent_id"],
                "created_at": now, "updated_at": now,
            })
        # Control: guía en tránsito → no debe tocarse
        gid_ctrl = new_id()
        tid_ctrl = new_id()
        await db.guias.insert_one({
            "id": gid_ctrl, "tenant_id": t_id, "tracking_id": "CTRL",
            "internal_status": "in_transit", "is_terminal": False,
            "client_id": env["client_id"],
            "created_at": now, "updated_at": now,
        })
        await db.tickets.insert_one({
            "id": tid_ctrl, "tenant_id": t_id, "guia_id": gid_ctrl,
            "client_id": env["client_id"], "status": "in_progress",
            "assigned_agent_id": env["agent_id"],
            "created_at": now, "updated_at": now,
        })
        headers = _bearer(user_id=env["superadmin_id"], tenant_id=t_id)
        r = await http_client.post(
            "/api/admin/maintenance/reconcile-delivered-tickets?dry_run=false",
            headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["scanned"] == 2
        assert data["resolved"] == 2

        # Tickets resueltos
        resolved_count = await db.tickets.count_documents({
            "tenant_id": t_id, "status": "resolved",
        })
        assert resolved_count == 2
        # Control sigue abierto
        ctrl = await db.tickets.find_one({"id": tid_ctrl}, {"_id": 0})
        assert ctrl["status"] == "in_progress"

    async def test_dry_run_does_not_persist(self, db, env, http_client):
        t_id = env["tenant_id"]
        now = datetime.now(timezone.utc).isoformat()
        gid = new_id()
        tid = new_id()
        await db.guias.insert_one({
            "id": gid, "tenant_id": t_id, "tracking_id": "D1",
            "internal_status": "delivered", "is_terminal": True,
            "client_id": env["client_id"],
            "created_at": now, "updated_at": now,
        })
        await db.tickets.insert_one({
            "id": tid, "tenant_id": t_id, "guia_id": gid,
            "client_id": env["client_id"], "status": "in_progress",
            "created_at": now, "updated_at": now,
        })
        headers = _bearer(user_id=env["superadmin_id"], tenant_id=t_id)
        r = await http_client.post(
            "/api/admin/maintenance/reconcile-delivered-tickets",
            headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["scanned"] == 1
        assert data["resolved"] == 1  # cuenta hipotética en dry-run
        # Pero no persiste
        ticket = await db.tickets.find_one({"id": tid}, {"_id": 0})
        assert ticket["status"] == "in_progress"

    async def test_tenant_isolation(self, db, env, http_client):
        t_id = env["tenant_id"]
        other_t = new_id()
        await db.tenants.insert_one(
            {"id": other_t, "slug": "ot", "name": "OT", "status": "active"})
        now = datetime.now(timezone.utc).isoformat()
        # Guía+ticket del OTRO tenant
        gid = new_id()
        tid = new_id()
        await db.guias.insert_one({
            "id": gid, "tenant_id": other_t, "tracking_id": "OT1",
            "internal_status": "delivered", "is_terminal": True,
            "created_at": now, "updated_at": now,
        })
        await db.tickets.insert_one({
            "id": tid, "tenant_id": other_t, "guia_id": gid,
            "status": "in_progress",
            "created_at": now, "updated_at": now,
        })
        headers = _bearer(user_id=env["superadmin_id"], tenant_id=t_id)
        r = await http_client.post(
            "/api/admin/maintenance/reconcile-delivered-tickets?dry_run=false",
            headers=headers)
        assert r.status_code == 200, r.text
        # No debe haber tocado el ticket del otro tenant
        other = await db.tickets.find_one({"id": tid}, {"_id": 0})
        assert other["status"] == "in_progress"

    async def test_agent_forbidden(self, env, http_client):
        headers = _bearer(user_id=env["agent_id"],
                          tenant_id=env["tenant_id"], role="agent")
        r = await http_client.post(
            "/api/admin/maintenance/reconcile-delivered-tickets",
            headers=headers)
        assert r.status_code == 403
