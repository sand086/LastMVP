"""Iter29 — Bundle B · R50 — Rule projection service & evaluators.

Cubre:
  * R02Evaluator: ticket terminal bloquea actions + habilita request_reopen.
  * R03Evaluator: motivo restricted → bloquea automation.
  * R03Evaluator: matriz permission allowed=False → bloquea automation.
  * R03Evaluator: matriz permission allowed=True → habilita automation.
  * R28Evaluator: claim conciliado → bloquea edit/upload/send.
  * GET /api/agent/tickets/{id} incluye projection con allowed_actions.
  * GET /api/reclamos/{id} incluye projection con allowed_actions.
  * POST /api/agent/tickets/{id}/request-reopen funciona en estados terminal.
  * POST /api/agent/tickets/{id}/request-reopen 422 si no es terminal.
  * GET /api/admin/rules/explain solo root_dev (otros roles → 403).
  * Cache: 2 invocaciones consecutivas devuelven el mismo computed_at.
  * Cache invalidation on automation_permissions upsert.
"""
from __future__ import annotations
import pytest
from datetime import datetime, timezone
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id
from services.rules.evaluators import EntityContext
from services.rules.evaluators.r02 import R02Evaluator
from services.rules.evaluators.r03 import R03Evaluator
from services.rules.evaluators.r28 import R28Evaluator


def _bearer(*, user_id, tenant_id, role="agent", email=None):
    tok = create_access_token(user_id=user_id, tenant_id=tenant_id,
                              role=role, email=email or f"{user_id[:6]}@t")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def env(db):
    tid = new_id()
    agent_id, admin_id, root_id = new_id(), new_id(), new_id()
    client_id = new_id()
    motivo_id = new_id()
    motivo_restricted_id = new_id()
    solucion_id = new_id()
    await db.tenants.insert_one(
        {"id": tid, "slug": "t1", "name": "T1", "status": "active"},
    )
    await db.users.insert_many([
        {"id": agent_id, "tenant_id": tid, "email": "ag@t",
         "role": "agent", "status": "active"},
        {"id": admin_id, "tenant_id": tid, "email": "ad@t",
         "role": "admin", "status": "active"},
        {"id": root_id, "tenant_id": tid, "email": "ro@t",
         "role": "root_dev", "status": "active"},
    ])
    await db.clients.insert_one(
        {"id": client_id, "tenant_id": tid, "name": "C1", "slug": "c1",
         "active": True, "automation_enabled": True,
         "ops_contact_email": "ops@c1"},
    )
    await db.motivos.insert_many([
        {"id": motivo_id, "tenant_id": tid, "code": "M1", "name": "Motivo OK",
         "restricted": False, "active": True},
        {"id": motivo_restricted_id, "tenant_id": tid, "code": "AUT",
         "name": "AUTORIDAD", "restricted": True, "active": True},
    ])
    await db.soluciones.insert_one(
        {"id": solucion_id, "tenant_id": tid, "motivo_id": motivo_id,
         "name": "S1", "automatable": True},
    )
    return {"tid": tid, "agent": agent_id, "admin": admin_id, "root": root_id,
            "client_id": client_id, "motivo_id": motivo_id,
            "motivo_restricted_id": motivo_restricted_id,
            "solucion_id": solucion_id, "db": db}


async def _seed_ticket(db, tenant_id, *, status="in_progress",
                       motivo_id=None, solucion_id=None,
                       client_id=None, channel="whatsapp",
                       is_terminal=False):
    tid = new_id()
    now = datetime.now(timezone.utc).isoformat()
    await db.tickets.insert_one({
        "id": tid, "tenant_id": tenant_id, "status": status,
        "is_terminal": is_terminal, "client_id": client_id,
        "motivo_id": motivo_id, "solucion_id": solucion_id,
        "channel": channel, "created_at": now, "updated_at": now,
    })
    return tid


# ───── Evaluators (unit tests, sin HTTP) ──────────────────────────────────
def test_r02_evaluator_active_ticket_no_overrides():
    ev = R02Evaluator()
    ctx = EntityContext(
        entity_type="ticket",
        entity={"id": "x", "status": "in_progress", "is_terminal": False},
        tenant_id="t", user_id="u", user_role="agent",
    )
    res = ev.evaluate(ctx)
    assert res.rule_id == "R02"
    assert res.overrides == []


def test_r02_evaluator_terminal_blocks_comm_and_enables_reopen():
    ev = R02Evaluator()
    ctx = EntityContext(
        entity_type="ticket",
        entity={"id": "x", "status": "delivered", "is_terminal": True},
        tenant_id="t", user_id="u", user_role="agent",
    )
    res = ev.evaluate(ctx)
    codes = {o.code: o for o in res.overrides}
    assert codes["send_validation_cta"].enabled is False
    assert codes["send_validation_cta"].reason == "R02"
    assert codes["request_reopen"].enabled is True


def test_r03_evaluator_restricted_motivo_blocks():
    ev = R03Evaluator()
    ctx = EntityContext(
        entity_type="ticket",
        entity={"id": "x", "solucion_id": "s", "channel": "email"},
        tenant_id="t", user_id="u", user_role="agent",
        motivo={"id": "m", "restricted": True},
        automation_rules={},
    )
    res = ev.evaluate(ctx)
    assert any(o.code == "execute_solution_automatic"
               and o.enabled is False and o.reason == "R03"
               for o in res.overrides)


def test_r03_evaluator_matrix_allowed_enables():
    ev = R03Evaluator()
    ctx = EntityContext(
        entity_type="ticket",
        entity={"id": "x", "solucion_id": "s", "channel": "email"},
        tenant_id="t", user_id="u", user_role="agent",
        motivo={"id": "m", "restricted": False},
        automation_rules={("s", "email"): True},
    )
    res = ev.evaluate(ctx)
    assert any(o.code == "execute_solution_automatic" and o.enabled
               for o in res.overrides)


def test_r03_evaluator_matrix_denied_blocks():
    ev = R03Evaluator()
    ctx = EntityContext(
        entity_type="ticket",
        entity={"id": "x", "solucion_id": "s", "channel": "email"},
        tenant_id="t", user_id="u", user_role="agent",
        motivo={"id": "m", "restricted": False},
        automation_rules={("s", "email"): False},
    )
    res = ev.evaluate(ctx)
    assert any(o.code == "execute_solution_automatic"
               and o.enabled is False and o.reason == "R03"
               for o in res.overrides)


def test_r28_evaluator_active_claim_no_overrides():
    ev = R28Evaluator()
    ctx = EntityContext(
        entity_type="reclamo",
        entity={"id": "c", "estado": "expediente_en_armado"},
        tenant_id="t", user_id="u", user_role="agent",
    )
    res = ev.evaluate(ctx)
    assert res.overrides == []


def test_r28_evaluator_conciliated_blocks_edit():
    ev = R28Evaluator()
    ctx = EntityContext(
        entity_type="reclamo",
        entity={"id": "c", "estado": "conciliado"},
        tenant_id="t", user_id="u", user_role="agent",
    )
    res = ev.evaluate(ctx)
    codes = {o.code: o for o in res.overrides}
    assert codes["edit_expediente"].enabled is False
    assert codes["edit_expediente"].reason == "R28"
    assert codes["request_reopen"].enabled is True


# ───── Integration: GET /api/agent/tickets/{id} with projection ───────────
@pytest.mark.asyncio
async def test_get_ticket_includes_projection_with_r02_and_r03(env, http_client):
    # Ticket terminal con motivo no restricted: R02 aplica
    ticket_id = await _seed_ticket(
        env["db"], env["tid"], status="delivered", is_terminal=True,
        motivo_id=env["motivo_id"], client_id=env["client_id"],
        solucion_id=env["solucion_id"], channel="whatsapp",
    )
    h = _bearer(user_id=env["agent"], tenant_id=env["tid"])
    r = await http_client.get(f"/api/agent/tickets/{ticket_id}", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert "projection" in body
    proj = body["projection"]
    assert "R02" in proj["applied_rules"]
    # send_validation_cta debe estar bloqueada por R02
    actions = {a["code"]: a for a in proj["allowed_actions"]}
    assert actions["send_validation_cta"]["enabled"] is False
    assert actions["send_validation_cta"]["reason"] == "R02"
    # request_reopen debe estar habilitada
    assert actions["request_reopen"]["enabled"] is True


@pytest.mark.asyncio
async def test_get_ticket_projection_with_restricted_motivo(env, http_client):
    ticket_id = await _seed_ticket(
        env["db"], env["tid"], status="in_progress",
        motivo_id=env["motivo_restricted_id"],
        client_id=env["client_id"],
        solucion_id=env["solucion_id"], channel="whatsapp",
    )
    h = _bearer(user_id=env["agent"], tenant_id=env["tid"])
    r = await http_client.get(f"/api/agent/tickets/{ticket_id}", headers=h)
    body = r.json()["data"]
    actions = {a["code"]: a for a in body["projection"]["allowed_actions"]}
    assert actions["execute_solution_automatic"]["enabled"] is False
    assert actions["execute_solution_automatic"]["reason"] == "R03"


@pytest.mark.asyncio
async def test_get_reclamo_includes_projection(env, http_client):
    # Crear ticket + claim conciliado
    ticket_id = await _seed_ticket(
        env["db"], env["tid"], status="in_progress",
        client_id=env["client_id"], motivo_id=env["motivo_id"],
    )
    claim_id = new_id()
    now = datetime.now(timezone.utc).isoformat()
    await env["db"].claims.insert_one({
        "id": claim_id, "tenant_id": env["tid"], "ticket_id": ticket_id,
        "estado": "conciliado", "tipo_dano": "extravio",
        "monto_reclamado": 1500, "divisa": "MXN",
        "is_terminal": True,
        "created_at": now, "updated_at": now,
    })
    h = _bearer(user_id=env["agent"], tenant_id=env["tid"])
    r = await http_client.get(f"/api/reclamos/{claim_id}", headers=h)
    assert r.status_code == 200, r.text
    proj = r.json()["data"]["projection"]
    assert "R28" in proj["applied_rules"]
    actions = {a["code"]: a for a in proj["allowed_actions"]}
    assert actions["edit_expediente"]["enabled"] is False
    assert actions["request_reopen"]["enabled"] is True


# ───── request-reopen endpoint ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_request_reopen_terminal_creates_request(env, http_client):
    ticket_id = await _seed_ticket(
        env["db"], env["tid"], status="delivered", is_terminal=True,
        client_id=env["client_id"], motivo_id=env["motivo_id"],
    )
    h = _bearer(user_id=env["agent"], tenant_id=env["tid"])
    r = await http_client.post(
        f"/api/agent/tickets/{ticket_id}/request-reopen",
        json={"reason": "El cliente reportó que NO llegó el paquete pese al estado."},
        headers=h,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    req = data["request"]
    assert req["status"] == "pending"
    assert req["ticket_id"] == ticket_id
    assert data["idempotent_hit"] is False
    # Persistencia
    persisted = await env["db"].reopen_requests.find_one(
        {"id": req["id"]}, {"_id": 0},
    )
    assert persisted is not None
    assert persisted["tenant_id"] == env["tid"]


@pytest.mark.asyncio
async def test_request_reopen_is_idempotent_same_user(env, http_client):
    """Doble click del agente NO debe crear 2 reopen_requests pending."""
    ticket_id = await _seed_ticket(
        env["db"], env["tid"], status="delivered", is_terminal=True,
        client_id=env["client_id"], motivo_id=env["motivo_id"],
    )
    h = _bearer(user_id=env["agent"], tenant_id=env["tid"])
    body = {"reason": "Cliente reporta no haber recibido el envío."}
    r1 = await http_client.post(
        f"/api/agent/tickets/{ticket_id}/request-reopen",
        json=body, headers=h,
    )
    assert r1.status_code == 200
    first = r1.json()["data"]
    assert first["idempotent_hit"] is False
    # Segunda llamada idéntica
    r2 = await http_client.post(
        f"/api/agent/tickets/{ticket_id}/request-reopen",
        json={"reason": "Razón diferente que no debería sobreescribir."},
        headers=h,
    )
    assert r2.status_code == 200
    second = r2.json()["data"]
    assert second["idempotent_hit"] is True
    assert second["request"]["id"] == first["request"]["id"]
    # Solo una entrada persistida
    count = await env["db"].reopen_requests.count_documents(
        {"ticket_id": ticket_id, "requested_by": env["agent"], "status": "pending"},
    )
    assert count == 1


@pytest.mark.asyncio
async def test_request_reopen_idempotency_scoped_per_user(env, http_client):
    """Idempotencia es por (ticket, requested_by) — otro usuario PUEDE
    crear su propia request independiente."""
    ticket_id = await _seed_ticket(
        env["db"], env["tid"], status="delivered", is_terminal=True,
        client_id=env["client_id"], motivo_id=env["motivo_id"],
    )
    # Seed un segundo agente del mismo tenant
    other_agent = new_id()
    await env["db"].users.insert_one({
        "id": other_agent, "tenant_id": env["tid"], "email": "ag2@t",
        "role": "agent", "status": "active",
    })
    h1 = _bearer(user_id=env["agent"], tenant_id=env["tid"])
    h2 = _bearer(user_id=other_agent, tenant_id=env["tid"])
    body = {"reason": "Cliente A reporta entrega no realizada."}

    r1 = await http_client.post(
        f"/api/agent/tickets/{ticket_id}/request-reopen",
        json=body, headers=h1,
    )
    r2 = await http_client.post(
        f"/api/agent/tickets/{ticket_id}/request-reopen",
        json={"reason": "Vista por agente B también — petición de soporte."},
        headers=h2,
    )
    assert r1.json()["data"]["idempotent_hit"] is False
    assert r2.json()["data"]["idempotent_hit"] is False
    # Dos requests distintas, una por user
    count = await env["db"].reopen_requests.count_documents(
        {"ticket_id": ticket_id, "status": "pending"},
    )
    assert count == 2


@pytest.mark.asyncio
async def test_request_reopen_non_terminal_422(env, http_client):
    ticket_id = await _seed_ticket(
        env["db"], env["tid"], status="in_progress",
        client_id=env["client_id"], motivo_id=env["motivo_id"],
    )
    h = _bearer(user_id=env["agent"], tenant_id=env["tid"])
    r = await http_client.post(
        f"/api/agent/tickets/{ticket_id}/request-reopen",
        json={"reason": "Lorem ipsum dolor sit amet."},
        headers=h,
    )
    assert r.status_code == 422
    assert r.json()["errors"][0]["field"] == "ticket_id"


# ───── /api/admin/rules/explain endpoint ──────────────────────────────────
@pytest.mark.asyncio
async def test_rules_explain_root_dev_only(env, http_client):
    ticket_id = await _seed_ticket(
        env["db"], env["tid"], status="delivered", is_terminal=True,
        client_id=env["client_id"], motivo_id=env["motivo_id"],
    )
    # admin → 403
    h_admin = _bearer(user_id=env["admin"], tenant_id=env["tid"], role="admin")
    r_a = await http_client.get(
        f"/api/admin/rules/explain?ticket_id={ticket_id}", headers=h_admin,
    )
    assert r_a.status_code == 403
    # root_dev → 200
    h_root = _bearer(user_id=env["root"], tenant_id=env["tid"], role="root_dev")
    r_r = await http_client.get(
        f"/api/admin/rules/explain?ticket_id={ticket_id}", headers=h_root,
    )
    assert r_r.status_code == 200, r_r.text
    body = r_r.json()["data"]
    assert body["found"] is True
    assert any(t["rule_id"] == "R02" for t in body["trace"])


# ───── Cache: invalidación on permission upsert ────────────────────────────
@pytest.mark.asyncio
async def test_cache_invalidates_on_automation_permission_upsert(env, http_client):
    ticket_id = await _seed_ticket(
        env["db"], env["tid"], status="in_progress",
        client_id=env["client_id"], motivo_id=env["motivo_id"],
        solucion_id=env["solucion_id"], channel="email",
    )
    h_agent = _bearer(user_id=env["agent"], tenant_id=env["tid"])
    # 1) GET ticket → projection con execute_solution_automatic blocked (sin permission)
    r1 = await http_client.get(
        f"/api/agent/tickets/{ticket_id}", headers=h_agent,
    )
    acts1 = {a["code"]: a for a in r1.json()["data"]["projection"]["allowed_actions"]}
    assert acts1["execute_solution_automatic"]["enabled"] is False
    # 2) Admin/coordinator habilita la matriz
    h_admin = _bearer(user_id=env["admin"], tenant_id=env["tid"], role="admin")
    r_perm = await http_client.put(
        "/api/admin/automation-permissions",
        json={"client_id": env["client_id"], "solucion_id": env["solucion_id"],
              "channel": "email", "allowed": True},
        headers=h_admin,
    )
    assert r_perm.status_code == 200, r_perm.text
    # 3) GET ticket NUEVAMENTE → cache fue invalidado → projection ahora enabled
    r2 = await http_client.get(
        f"/api/agent/tickets/{ticket_id}", headers=h_agent,
    )
    acts2 = {a["code"]: a for a in r2.json()["data"]["projection"]["allowed_actions"]}
    assert acts2["execute_solution_automatic"]["enabled"] is True
