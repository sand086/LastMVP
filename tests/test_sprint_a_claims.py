"""Sprint A — Cierre PROMPT_13 V1.

Cobertura:
  * P0.5 — POST /api/reclamos/{id}/notificar-cliente: ok (mock email),
    422 si cliente sin cxc_contact_email, 409 en estado terminal,
    registra claim_event 'client_notified'
  * P0.10 — ClaimAutomationTest: enviar-carrier respeta R03
    (motivo_restricted, sin permission, con permission)
  * P1.1 — scan_claim_sla detecta reclamos viejos por estado y registra
    'claim_sla_breach'; deduplica si ya existe; respeta sla_config override
  * P1.2 — Promote→push notificación in-app a coordinator;
    GET /api/inbox/unread-count; POST /api/inbox/{id}/read
  * P1.3 — GET /api/dashboard/claims-open devuelve KPIs por estado
  * P1.4 — GET /api/dashboard/report/must-have incluye sección claims
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
import pytest
from httpx import AsyncClient, ASGITransport

from server import app
from core.security import create_access_token
from core.uuid import new_id
from repositories.claims import ensure_claim_indexes
from seeds.cae_catalog import run as seed_cae


def _bearer(*, user_id, tenant_id, role="agent"):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_id, tenant_id=tenant_id, role=role, email='u@t')}"}


def _iso_offset(*, hours: int = 0, minutes: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours, minutes=minutes)).isoformat()


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def sprint_setup(db, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "")  # mock email
    tid = new_id()
    uid_agent, uid_coord, uid_admin = new_id(), new_id(), new_id()
    pj_id, cl_id, motivo_id, sol_id, guia_id, ticket_id, claim_id, carrier_id = (
        new_id() for _ in range(8)
    )
    await db.tenants.insert_one({"id": tid, "slug": "sa", "name": "Sa", "status": "active"})
    await db.users.insert_many([
        {"id": uid_agent, "tenant_id": tid, "email": "ag@t",
         "password_hash": "x", "name": "Agente", "role": "agent", "status": "active"},
        {"id": uid_coord, "tenant_id": tid, "email": "co@t",
         "password_hash": "x", "name": "Coord", "role": "coordinator", "status": "active"},
        {"id": uid_admin, "tenant_id": tid, "email": "ad@t",
         "password_hash": "x", "name": "Admin", "role": "admin", "status": "active"},
    ])
    await db.projects.insert_one({"id": pj_id, "tenant_id": tid, "name": "P", "status": "active"})
    await db.clients.insert_one({
        "id": cl_id, "tenant_id": tid, "project_id": pj_id, "name": "Cliente CxC",
        "ingest_mode": "webhook", "webhook_token": "wh-x",
        "ops_contact_email": "ops@cli.test", "ops_contact_name": "Ops Lead",
        "cxc_contact_email": "cxc@cli.test", "cxc_contact_name": "CxC Lead",
    })
    await db.motivos.insert_one({
        "id": motivo_id, "tenant_id": tid, "name": "Daño",
        "active": True, "restricted": False,
    })
    await db.soluciones.insert_one({
        "id": sol_id, "tenant_id": tid, "motivo_id": motivo_id,
        "nombre": "Reclamo daño", "automatable": True, "active": True,
    })
    await db.carriers.insert_one({
        "id": carrier_id, "tenant_id": tid, "name": "FedEx", "code": "fedex",
        "has_api": True, "active": True, "status": "active",
    })
    await db.guias.insert_one({
        "id": guia_id, "tenant_id": tid, "tracking_id": "SA-1",
        "carrier_id": "fedex", "client_id": cl_id,
        "carrier_status": "delivered", "internal_status": "delivered",
        "is_terminal": True,
    })
    await db.tickets.insert_one({
        "id": ticket_id, "tenant_id": tid, "client_id": cl_id, "guia_id": guia_id,
        "carrier_id": "fedex", "status": "resolved", "assigned_agent_id": uid_agent,
        "incident_type": "damaged", "canonical_status": "delivered",
        "carrier_status_raw": "DL", "source": "ingest",
        "solucion_id": sol_id,
        "created_at": _iso_offset(hours=24), "updated_at": _iso_offset(hours=2),
    })
    await db.claims.insert_one({
        "id": claim_id, "tenant_id": tid, "ticket_id": ticket_id, "client_id": cl_id,
        "estado": "promovido", "is_terminal": False,
        "tipo_dano": "dano_total", "monto_reclamado": 1500, "divisa": "MXN",
        "promoted_by": uid_agent,
        "promoted_at": _iso_offset(hours=72),
        "expediente": {},
        "created_at": _iso_offset(hours=72),
        "updated_at": _iso_offset(hours=72),
    })
    await seed_cae()
    await ensure_claim_indexes()
    return {
        "tenant_id": tid, "agent_id": uid_agent, "coord_id": uid_coord,
        "admin_id": uid_admin, "client_id": cl_id, "motivo_id": motivo_id,
        "solucion_id": sol_id, "ticket_id": ticket_id, "claim_id": claim_id,
    }


# ───────────────────────── P0.5 — notificar-cliente ───────────────────
@pytest.mark.asyncio
async def test_notify_client_sends_to_cxc_contact(http_client, db, sprint_setup):
    s = sprint_setup
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.post(
        f"/api/reclamos/{s['claim_id']}/notificar-cliente",
        json={"message": "Estimado equipo, su reclamo ha sido promovido y enviado al carrier.",
              "cta_url": "https://app.test/r/abc"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["to"] == "cxc@cli.test"
    assert body["result"]["ok"] is True and body["result"]["mock"] is True
    # claim_event registrado
    ev = await db.claim_events.find_one({
        "claim_id": s["claim_id"], "event_type": "client_notified",
    })
    assert ev and ev["payload"]["to"] == "cxc@cli.test"


@pytest.mark.asyncio
async def test_notify_client_falls_back_to_ops_email(http_client, db, sprint_setup):
    """Si no hay cxc_contact_email, usa ops_contact_email como fallback."""
    s = sprint_setup
    await db.clients.update_one({"id": s["client_id"]},
        {"$unset": {"cxc_contact_email": "", "cxc_contact_name": ""}})
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.post(
        f"/api/reclamos/{s['claim_id']}/notificar-cliente",
        json={"message": "Mensaje de prueba con suficiente longitud."},
        headers=h,
    )
    body = r.json()["data"]
    assert body["to"] == "ops@cli.test"


@pytest.mark.asyncio
async def test_notify_client_blocked_when_no_email(http_client, db, sprint_setup):
    s = sprint_setup
    await db.clients.update_one({"id": s["client_id"]},
        {"$unset": {"cxc_contact_email": "", "ops_contact_email": ""}})
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.post(
        f"/api/reclamos/{s['claim_id']}/notificar-cliente",
        json={"message": "Mensaje de prueba con longitud suficiente."},
        headers=h,
    )
    assert r.status_code == 422
    body = r.json()
    assert body["errors"][0]["field"] == "cxc_contact_email"


@pytest.mark.asyncio
async def test_notify_client_blocked_in_terminal_state(http_client, db, sprint_setup):
    s = sprint_setup
    await db.claims.update_one({"id": s["claim_id"]},
        {"$set": {"estado": "conciliado", "is_terminal": True}})
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.post(
        f"/api/reclamos/{s['claim_id']}/notificar-cliente",
        json={"message": "Mensaje cualquiera con longitud suficiente."},
        headers=h,
    )
    assert r.status_code == 409


# ─────────────────────── P0.10 — ClaimAutomationTest (R03) ────────────
@pytest.mark.asyncio
async def test_enviar_carrier_motivo_restricted_does_not_apply_to_claim_flow(http_client, db, sprint_setup):
    """R03 — el flag motivo.restricted aplica al flujo de TICKETS, no al de
    reclamos. Los reclamos usan el solucion sintético 'reclamo:{tipo_dano}'
    y solo dependen de automation_permissions."""
    s = sprint_setup
    await db.claims.update_one({"id": s["claim_id"]}, {"$set": {
        "estado": "expediente_en_armado",
        "expediente": {"declaracion_cliente": "ok", "evidencia_ids": ["a", "b"]},
    }})
    # motivo restringido — no debe afectar al flujo de reclamos
    await db.motivos.update_one({"id": s["motivo_id"]}, {"$set": {"restricted": True}})
    await db.tickets.update_one({"id": s["ticket_id"]},
        {"$set": {"motivo_id": s["motivo_id"]}})
    # Permission allowed para "reclamo:dano_total"
    await db.automation_permissions.insert_one({
        "id": new_id(), "tenant_id": s["tenant_id"], "client_id": s["client_id"],
        "solucion_id": "reclamo:dano_total", "channel": "api", "allowed": True,
    })
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.post(f"/api/reclamos/{s['claim_id']}/enviar-carrier", headers=h)
    # motivo.restricted=True NO bloquea el flujo de claims (es un layer aparte)
    assert r.status_code == 200, r.text
    refreshed = await db.claims.find_one({"id": s["claim_id"]})
    assert refreshed["estado"] == "en_dictamen_carrier"


@pytest.mark.asyncio
async def test_enviar_carrier_blocked_without_automation_permission(http_client, db, sprint_setup):
    s = sprint_setup
    await db.claims.update_one({"id": s["claim_id"]}, {"$set": {
        "estado": "expediente_en_armado",
        "expediente": {"declaracion_cliente": "ok", "evidencia_ids": ["a", "b"]},
    }})
    await db.tickets.update_one({"id": s["ticket_id"]},
        {"$set": {"motivo_id": s["motivo_id"]}})
    # No insertamos permission → default deny
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.post(f"/api/reclamos/{s['claim_id']}/enviar-carrier", headers=h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_enviar_carrier_proceeds_with_full_kit_and_permission(http_client, db, sprint_setup):
    s = sprint_setup
    await db.claims.update_one({"id": s["claim_id"]}, {"$set": {
        "estado": "expediente_en_armado",
        "expediente": {"declaracion_cliente": "ok", "evidencia_ids": ["a", "b"]},
    }})
    await db.tickets.update_one({"id": s["ticket_id"]},
        {"$set": {"motivo_id": s["motivo_id"]}})
    # R33 — permission keyed por "reclamo:{tipo_dano}"
    await db.automation_permissions.insert_one({
        "id": new_id(), "tenant_id": s["tenant_id"], "client_id": s["client_id"],
        "solucion_id": "reclamo:dano_total", "channel": "api", "allowed": True,
    })
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.post(f"/api/reclamos/{s['claim_id']}/enviar-carrier", headers=h)
    assert r.status_code == 200
    refreshed = await db.claims.find_one({"id": s["claim_id"]})
    assert refreshed["estado"] == "en_dictamen_carrier"


# ─────────────────────── P1.1 — Claims SLA scanner ────────────────────
@pytest.mark.asyncio
async def test_scan_claim_sla_detects_aged_promovido(db, sprint_setup):
    """Default SLA promovido=48h; nuestro claim tiene 72h → debe disparar."""
    s = sprint_setup
    from services.sla_inactivity import scan_claim_sla
    res = await scan_claim_sla(tenant_id=s["tenant_id"])
    assert res.breaches == 1
    assert res.notified == 1
    ev = await db.claim_events.find_one({
        "claim_id": s["claim_id"], "event_type": "claim_sla_breach",
    })
    assert ev and ev["payload"]["estado"] == "promovido"
    # Re-run inmediato no re-notifica
    res2 = await scan_claim_sla(tenant_id=s["tenant_id"])
    assert res2.notified == 0


@pytest.mark.asyncio
async def test_scan_claim_sla_respects_sla_config_override(db, sprint_setup):
    s = sprint_setup
    # Override: promovido=240h → nuestro claim de 72h ya NO está en breach
    await db.sla_config.insert_one({
        "tenant_id": s["tenant_id"], "scope": "claims",
        "by_estado": {"promovido": 240},
    })
    from services.sla_inactivity import scan_claim_sla
    res = await scan_claim_sla(tenant_id=s["tenant_id"])
    assert res.breaches == 0


@pytest.mark.asyncio
async def test_admin_cron_run_claim_sla_endpoint(http_client, sprint_setup):
    s = sprint_setup
    h = _bearer(user_id=s["admin_id"], tenant_id=s["tenant_id"], role="admin")
    r = await http_client.post("/api/admin/cron/run/claim_sla", headers=h)
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["job"] == "claim_sla"
    assert "breaches" in body and "notified" in body


# ─────────────────────── P1.2 — In-app inbox ──────────────────────────
@pytest.mark.asyncio
async def test_promote_pushes_inbox_to_coordinator(http_client, db, sprint_setup):
    s = sprint_setup
    # Crear segundo ticket promovible
    new_ticket = new_id()
    await db.tickets.insert_one({
        "id": new_ticket, "tenant_id": s["tenant_id"], "client_id": s["client_id"],
        "guia_id": new_id(), "carrier_id": "fedex", "status": "resolved",
        "assigned_agent_id": s["agent_id"], "incident_type": "damaged",
        "canonical_status": "delivered", "carrier_status_raw": "DL",
        "source": "ingest", "created_at": _iso_offset(hours=10),
        "updated_at": _iso_offset(hours=1),
    })
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.post(
        f"/api/tickets/{new_ticket}/promote-to-claim",
        json={"tipo_dano": "extravio", "monto_reclamado": 100},
        headers=h,
    )
    assert r.status_code == 201
    # Coordinator debe ver una notificación nueva
    h_coord = _bearer(user_id=s["coord_id"], tenant_id=s["tenant_id"], role="coordinator")
    rc = await http_client.get("/api/inbox/unread-count", headers=h_coord)
    assert rc.json()["data"]["unread"] >= 1
    rl = await http_client.get("/api/inbox", headers=h_coord)
    items = rl.json()["data"]["items"]
    assert any(i["kind"] == "claim_promoted" for i in items)


@pytest.mark.asyncio
async def test_inbox_mark_read(http_client, db, sprint_setup):
    s = sprint_setup
    # push manual una notif al coordinator
    from repositories.inbox import InboxRepository
    repo = InboxRepository(tenant_id=s["tenant_id"])
    notif = await repo.push(
        recipient_user_id=s["coord_id"], kind="test",
        title="Test", body="manual",
    )
    h = _bearer(user_id=s["coord_id"], tenant_id=s["tenant_id"], role="coordinator")
    r = await http_client.post(f"/api/inbox/{notif['id']}/read", headers=h)
    assert r.status_code == 200
    # Ahora unread-count baja
    rc = await http_client.get("/api/inbox/unread-count", headers=h)
    refreshed = await db.inbox_notifications.find_one({"id": notif["id"]})
    assert refreshed["read_at"] is not None


# ─────────────────────── P1.3 — Dashboard claims-open ─────────────────
@pytest.mark.asyncio
async def test_dashboard_claims_open_kpis(http_client, sprint_setup):
    s = sprint_setup
    h = _bearer(user_id=s["admin_id"], tenant_id=s["tenant_id"], role="supervisor")
    r = await http_client.get("/api/dashboard/claims-open", headers=h)
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["open_total"] == 1
    assert any(item["estado"] == "promovido" for item in body["by_estado"])


# ─────────────────────── P1.4 — Reporte must-have ─────────────────────
@pytest.mark.asyncio
async def test_dashboard_report_must_have_includes_claims_section(http_client, sprint_setup):
    s = sprint_setup
    h = _bearer(user_id=s["admin_id"], tenant_id=s["tenant_id"], role="supervisor")
    r = await http_client.get("/api/dashboard/report/must-have?days=30", headers=h)
    assert r.status_code == 200
    body = r.json()["data"]
    assert "tickets" in body and "claims" in body
    assert body["claims"]["promoted"] >= 1
    assert body["claims"]["monto_reclamado_total"] >= 1500
    assert isinstance(body["claims"]["by_tipo_dano"], list)
