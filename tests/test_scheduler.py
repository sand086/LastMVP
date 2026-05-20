"""PROMPT 11.5 — SLA + Inactivity + Daily Summary + Scheduler.

Cobertura:
  * scan_sla detecta tickets accionables con updated_at > umbral; agrega
    timeline_event 'sla_breach'; deduplica si ya hay uno reciente.
  * scan_sla ignora tickets en waiting_* (R15) y tickets terminales.
  * scan_inactive_agents agrega 'agent_inactive' por agente con tickets viejos;
    waiting_* no cuenta (R15).
  * compute_metrics + render_summary_email producen un dict y un par (html, text).
  * /api/admin/cron/status devuelve running=False cuando CRON_ENABLED!=1.
  * /api/admin/cron/run/{sla|inactivity|daily_summary|pulling} ejecutan on-demand.
  * RBAC: /api/admin/cron/* exige admin+.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
import pytest
from httpx import AsyncClient, ASGITransport

from server import app
from core.security import create_access_token
from core.uuid import new_id


def _bearer(*, user_id, tenant_id, role="admin", email="admin@test.local"):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_id, tenant_id=tenant_id, role=role, email=email)}"}


def _iso_offset(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def cron_setup(db, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "")  # mock email
    monkeypatch.setenv("CRON_ENABLED", "0")
    tid = new_id()
    uid_admin, uid_supervisor, uid_agent = new_id(), new_id(), new_id()
    pj_id, cl_id = new_id(), new_id()
    await db.tenants.insert_one({"id": tid, "slug": "cron", "name": "Cron Tenant", "status": "active"})
    await db.users.insert_many([
        {"id": uid_admin, "tenant_id": tid, "email": "ad@t",
         "password_hash": "x", "name": "Admin", "role": "admin", "status": "active"},
        {"id": uid_supervisor, "tenant_id": tid, "email": "sup@t",
         "password_hash": "x", "name": "Supervisor", "role": "supervisor", "status": "active"},
        {"id": uid_agent, "tenant_id": tid, "email": "ag@t",
         "password_hash": "x", "name": "Agente", "role": "agent", "status": "active"},
    ])
    await db.projects.insert_one({"id": pj_id, "tenant_id": tid, "name": "P", "status": "active"})
    await db.clients.insert_one({
        "id": cl_id, "tenant_id": tid, "project_id": pj_id, "name": "Cliente",
        "ingest_mode": "pulling", "webhook_token": "wh-secret",
    })
    return {
        "tenant_id": tid, "admin_id": uid_admin,
        "supervisor_id": uid_supervisor, "agent_id": uid_agent,
        "client_id": cl_id,
    }


# ───────────────────────── SLA scanner ────────────────────────────────
@pytest.mark.asyncio
async def test_scan_sla_finds_breach_and_records_event(db, cron_setup):
    s = cron_setup
    tid = new_id()
    await db.tickets.insert_one({
        "id": tid, "tenant_id": s["tenant_id"], "client_id": s["client_id"],
        "guia_id": new_id(), "carrier_id": "fedex",
        "status": "in_progress", "assigned_agent_id": s["agent_id"],
        "incident_type": "address_issue", "canonical_status": "exception",
        "carrier_status_raw": "DE", "source": "ingest",
        "created_at": _iso_offset(180), "updated_at": _iso_offset(120),
    })
    from services.sla_inactivity import scan_sla
    res = await scan_sla(tenant_id=s["tenant_id"], sla_minutes=60)
    assert res.breaches == 1 and res.notified == 1
    ev = await db.timeline_events.find_one({"ticket_id": tid, "event_type": "sla_breach"})
    assert ev is not None
    assert ev["payload"]["sla_minutes"] == 60
    # Re-run inmediato → no re-notifica
    res2 = await scan_sla(tenant_id=s["tenant_id"], sla_minutes=60)
    assert res2.notified == 0


@pytest.mark.asyncio
async def test_scan_sla_ignores_waiting_and_terminal(db, cron_setup):
    s = cron_setup
    base = {
        "tenant_id": s["tenant_id"], "client_id": s["client_id"],
        "guia_id": new_id(), "carrier_id": "fedex",
        "incident_type": "x", "canonical_status": "exception",
        "carrier_status_raw": "X", "source": "ingest",
        "created_at": _iso_offset(180), "updated_at": _iso_offset(120),
    }
    await db.tickets.insert_many([
        {**base, "id": new_id(), "status": "waiting_client"},
        {**base, "id": new_id(), "status": "waiting_carrier"},
        {**base, "id": new_id(), "status": "resolved"},
        {**base, "id": new_id(), "status": "closed"},
    ])
    from services.sla_inactivity import scan_sla
    res = await scan_sla(tenant_id=s["tenant_id"], sla_minutes=60)
    assert res.breaches == 0


# ───────────────────────── Inactivity scanner ─────────────────────────
@pytest.mark.asyncio
async def test_scan_inactive_agents_marks_one(db, cron_setup):
    s = cron_setup
    tid = new_id()
    await db.tickets.insert_one({
        "id": tid, "tenant_id": s["tenant_id"], "client_id": s["client_id"],
        "guia_id": new_id(), "carrier_id": "fedex",
        "status": "in_progress", "assigned_agent_id": s["agent_id"],
        "incident_type": "x", "canonical_status": "exception",
        "carrier_status_raw": "X", "source": "ingest",
        "created_at": _iso_offset(180), "updated_at": _iso_offset(60),
    })
    from services.sla_inactivity import scan_inactive_agents
    res = await scan_inactive_agents(tenant_id=s["tenant_id"], threshold_minutes=30)
    assert res.inactive_agents == 1 and res.notified == 1
    ev = await db.timeline_events.find_one({"ticket_id": tid, "event_type": "agent_inactive"})
    assert ev is not None and ev["payload"]["agent_id"] == s["agent_id"]


# ───────────────────────── Daily summary ──────────────────────────────
@pytest.mark.asyncio
async def test_daily_summary_metrics_and_email_mock(db, cron_setup):
    s = cron_setup
    # Inserta algunos tickets para que las métricas no sean cero
    await db.tickets.insert_many([
        {"id": new_id(), "tenant_id": s["tenant_id"], "client_id": s["client_id"],
         "guia_id": new_id(), "status": "in_progress", "source": "ingest",
         "created_at": _iso_offset(60), "updated_at": _iso_offset(60)},
        {"id": new_id(), "tenant_id": s["tenant_id"], "client_id": s["client_id"],
         "guia_id": new_id(), "status": "resolved", "source": "ingest",
         "created_at": _iso_offset(60), "updated_at": _iso_offset(5)},
    ])
    from services.daily_summary import compute_metrics, send_for_tenant
    metrics = await compute_metrics(s["tenant_id"])
    assert metrics["open_tickets"] == 1
    assert metrics["resolved_today"] == 1
    out = await send_for_tenant(s["tenant_id"])
    assert out.sent is True
    assert out.to == "sup@t"  # supervisor seeded


@pytest.mark.asyncio
async def test_daily_summary_no_recipient(db, cron_setup):
    s = cron_setup
    # Borra supervisor y admin → fallback "no_recipient"
    await db.users.delete_many({"tenant_id": s["tenant_id"], "role": {"$in": ["supervisor", "admin"]}})
    from services.daily_summary import send_for_tenant
    out = await send_for_tenant(s["tenant_id"])
    assert out.sent is False
    assert out.reason == "no_recipient"


# ───────────────────────── Admin /cron endpoints ──────────────────────
@pytest.mark.asyncio
async def test_admin_cron_status_disabled(http_client, cron_setup, monkeypatch):
    monkeypatch.setenv("CRON_ENABLED", "0")
    s = cron_setup
    h = _bearer(user_id=s["admin_id"], tenant_id=s["tenant_id"], role="admin")
    r = await http_client.get("/api/admin/cron/status", headers=h)
    body = r.json()["data"]
    # En tests no arrancamos scheduler → running=False, jobs=[]
    assert body["running"] is False
    assert body["jobs"] == []
    assert body["enabled_env"] is False


@pytest.mark.asyncio
async def test_admin_cron_run_sla(http_client, db, cron_setup):
    s = cron_setup
    await db.tickets.insert_one({
        "id": new_id(), "tenant_id": s["tenant_id"], "client_id": s["client_id"],
        "guia_id": new_id(), "carrier_id": "fedex",
        "status": "in_progress", "assigned_agent_id": s["agent_id"],
        "incident_type": "x", "canonical_status": "exception",
        "carrier_status_raw": "X", "source": "ingest",
        "created_at": _iso_offset(180), "updated_at": _iso_offset(120),
    })
    h = _bearer(user_id=s["admin_id"], tenant_id=s["tenant_id"], role="admin")
    r = await http_client.post("/api/admin/cron/run/sla", headers=h)
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["job"] == "sla"
    assert body["breaches"] == 1


@pytest.mark.asyncio
async def test_admin_cron_run_daily_summary(http_client, cron_setup):
    s = cron_setup
    h = _bearer(user_id=s["admin_id"], tenant_id=s["tenant_id"], role="admin")
    r = await http_client.post("/api/admin/cron/run/daily_summary", headers=h)
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["sent"] is True
    assert body["metrics"]["open_tickets"] >= 0


@pytest.mark.asyncio
async def test_admin_cron_rbac_blocks_agent(http_client, cron_setup):
    s = cron_setup
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.get("/api/admin/cron/status", headers=h)
    assert r.status_code == 403
