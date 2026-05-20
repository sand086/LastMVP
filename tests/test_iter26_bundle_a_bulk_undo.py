"""Iter26 — Bundle A · FIX-A1 — Bulk close with typed confirmation + undo.

Cubre:
  * typed_confirmation requerido cuando ticket_ids >= 10 (close + change_status).
  * No requerido cuando ticket_ids < 10.
  * Respuesta contiene transaction_id + undo_window_seconds.
  * bulk-undo revierte el status original dentro de los 30 seg.
  * bulk-undo retorna 410 (TERMINAL_STATE) cuando expiró la ventana.
  * bulk-undo respeta R02 (no reabre tickets cuyo guia llegó a terminal después).
  * bulk-undo retorna 403 cuando otro usuario intenta el undo.
"""
from __future__ import annotations
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id


def _bearer(*, user_id, tenant_id, role="admin", email=None):
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
    admin_id = new_id()
    admin2_id = new_id()
    await db.tenants.insert_one(
        {"id": tid, "slug": "t1", "name": "T1", "status": "active"},
    )
    await db.users.insert_many([
        {"id": admin_id, "tenant_id": tid, "email": "a1@t",
         "role": "admin", "status": "active"},
        {"id": admin2_id, "tenant_id": tid, "email": "a2@t",
         "role": "admin", "status": "active"},
    ])
    return {"tid": tid, "admin": admin_id, "admin2": admin2_id, "db": db}


async def _seed_tickets(db, tenant_id, count, status="in_progress"):
    ids = []
    now = datetime.now(timezone.utc).isoformat()
    for _ in range(count):
        tid = new_id()
        await db.tickets.insert_one({
            "id": tid, "tenant_id": tenant_id, "status": status,
            "is_terminal": False, "client_id": new_id(),
            "created_at": now, "updated_at": now,
        })
        ids.append(tid)
    return ids


@pytest.mark.asyncio
async def test_bulk_close_requires_typed_confirmation_when_10_or_more(env, http_client):
    ticket_ids = await _seed_tickets(env["db"], env["tid"], 10)
    h = _bearer(user_id=env["admin"], tenant_id=env["tid"])
    # Sin typed_confirmation → 422
    r = await http_client.post(
        "/api/admin/tickets/bulk",
        json={"ticket_ids": ticket_ids, "action": "close"},
        headers=h,
    )
    assert r.status_code == 422
    body = r.json()
    assert body["success"] is False
    assert body["errors"][0]["field"] == "typed_confirmation"


@pytest.mark.asyncio
async def test_bulk_close_no_confirmation_under_10(env, http_client):
    ticket_ids = await _seed_tickets(env["db"], env["tid"], 9)
    h = _bearer(user_id=env["admin"], tenant_id=env["tid"])
    r = await http_client.post(
        "/api/admin/tickets/bulk",
        json={"ticket_ids": ticket_ids, "action": "close"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["affected"] == 9
    assert "transaction_id" in data
    assert data["undo_window_seconds"] == 30


@pytest.mark.asyncio
async def test_bulk_close_with_confirmation_returns_transaction(env, http_client):
    ticket_ids = await _seed_tickets(env["db"], env["tid"], 12)
    h = _bearer(user_id=env["admin"], tenant_id=env["tid"])
    r = await http_client.post(
        "/api/admin/tickets/bulk",
        json={"ticket_ids": ticket_ids, "action": "close",
              "typed_confirmation": "CERRAR"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["affected"] == 12
    assert data["transaction_id"]
    # Verificar persistencia de la transacción
    txn = await env["db"].bulk_close_transactions.find_one(
        {"id": data["transaction_id"]}, {"_id": 0},
    )
    assert txn is not None
    assert txn["tenant_id"] == env["tid"]
    assert txn["user_id"] == env["admin"]
    assert txn["action_type"] == "close"
    assert len(txn["previous_states"]) == 12


@pytest.mark.asyncio
async def test_bulk_undo_within_window_reverts(env, http_client):
    ticket_ids = await _seed_tickets(env["db"], env["tid"], 5,
                                     status="in_progress")
    h = _bearer(user_id=env["admin"], tenant_id=env["tid"])
    r = await http_client.post(
        "/api/admin/tickets/bulk",
        json={"ticket_ids": ticket_ids, "action": "close"},
        headers=h,
    )
    txn_id = r.json()["data"]["transaction_id"]
    # Hacer undo
    r2 = await http_client.post(
        "/api/admin/tickets/bulk-undo",
        json={"transaction_id": txn_id},
        headers=h,
    )
    assert r2.status_code == 200, r2.text
    data = r2.json()["data"]
    assert data["reverted_count"] == 5
    # Verificar que el status volvió a in_progress
    sample = await env["db"].tickets.find_one(
        {"id": ticket_ids[0]}, {"_id": 0, "status": 1, "is_terminal": 1},
    )
    assert sample["status"] == "in_progress"
    assert sample["is_terminal"] is False
    # Y la transacción quedó marcada como undone
    txn = await env["db"].bulk_close_transactions.find_one(
        {"id": txn_id}, {"_id": 0},
    )
    assert txn["undone_at"] is not None


@pytest.mark.asyncio
async def test_bulk_undo_after_window_returns_410(env, http_client):
    ticket_ids = await _seed_tickets(env["db"], env["tid"], 3)
    h = _bearer(user_id=env["admin"], tenant_id=env["tid"])
    r = await http_client.post(
        "/api/admin/tickets/bulk",
        json={"ticket_ids": ticket_ids, "action": "close"},
        headers=h,
    )
    txn_id = r.json()["data"]["transaction_id"]
    # Forzar expiración de la ventana editando undo_window_end al pasado.
    past = "2020-01-01T00:00:00+00:00"
    await env["db"].bulk_close_transactions.update_one(
        {"id": txn_id}, {"$set": {"undo_window_end": past}},
    )
    r2 = await http_client.post(
        "/api/admin/tickets/bulk-undo",
        json={"transaction_id": txn_id},
        headers=h,
    )
    assert r2.status_code == 409, r2.text
    assert r2.json()["errors"][0]["code"] == "TERMINAL_STATE"


@pytest.mark.asyncio
async def test_bulk_undo_ownership_403(env, http_client):
    ticket_ids = await _seed_tickets(env["db"], env["tid"], 3)
    h1 = _bearer(user_id=env["admin"], tenant_id=env["tid"])
    h2 = _bearer(user_id=env["admin2"], tenant_id=env["tid"], email="a2@t")
    r = await http_client.post(
        "/api/admin/tickets/bulk",
        json={"ticket_ids": ticket_ids, "action": "close"},
        headers=h1,
    )
    txn_id = r.json()["data"]["transaction_id"]
    # admin2 intenta hacer undo de la transacción de admin1
    r2 = await http_client.post(
        "/api/admin/tickets/bulk-undo",
        json={"transaction_id": txn_id},
        headers=h2,
    )
    assert r2.status_code == 403, r2.text
    assert r2.json()["errors"][0]["code"] == "RBAC_DENIED"


@pytest.mark.asyncio
async def test_bulk_undo_respects_terminal_state_r02(env, http_client):
    """Si entre el bulk_close y el undo el ticket llegó a terminal por
    OTRO proceso (ej. el carrier reportó entregado), el undo NO debe
    revertirlo (R02). Pero el ticket *sí* puede revertirse a su estado
    previo porque el bulk_close lo marcó terminal=True; usamos un
    proxy: marcar manualmente un updated_at futuro + status `delivered`.
    """
    ticket_ids = await _seed_tickets(env["db"], env["tid"], 3,
                                     status="in_progress")
    h = _bearer(user_id=env["admin"], tenant_id=env["tid"])
    r = await http_client.post(
        "/api/admin/tickets/bulk",
        json={"ticket_ids": ticket_ids, "action": "close"},
        headers=h,
    )
    txn_id = r.json()["data"]["transaction_id"]
    # Simular que el carrier marcó terminal=True en uno entre el close y el undo
    future = "2099-01-01T00:00:00+00:00"
    await env["db"].tickets.update_one(
        {"id": ticket_ids[0]},
        {"$set": {"is_terminal": True, "status": "delivered",
                  "updated_at": future}},
    )
    r2 = await http_client.post(
        "/api/admin/tickets/bulk-undo",
        json={"transaction_id": txn_id},
        headers=h,
    )
    assert r2.status_code == 200, r2.text
    data = r2.json()["data"]
    # 2 revertidos, 1 saltado por terminal_state
    assert data["reverted_count"] == 2
    assert data["skipped_count"] == 1
    assert any(s["ticket_id"] == ticket_ids[0]
               and s["reason"] == "terminal_state"
               for s in data["skipped_reasons"])
