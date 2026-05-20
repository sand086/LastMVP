"""PROMPT 04 — Ingest tests.

Coverage:
  * Webhook with valid HMAC creates guía
  * Webhook with invalid HMAC → 401 AUTH_REQUIRED
  * Webhook update → 'updated', no duplicate guías
  * Same status twice → 'discarded_no_change'
  * Terminal guía silently ignored on subsequent webhook (R02)
  * CSV layout upload creates multiple guías
  * Non-CSV upload rejected
"""
from __future__ import annotations
import json
import pytest
from httpx import AsyncClient, ASGITransport

from server import app
from core.hmac import sign
from core.security import create_access_token
from core.uuid import new_id


def _bearer(*, user_id, tenant_id, role="admin", email="admin@test.local"):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_id, tenant_id=tenant_id, role=role, email=email)}"}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def setup(db):
    """Create a tenant, an admin user, a project, and a webhook client."""
    tid = new_id()
    uid = new_id()
    pj = new_id()
    cid = new_id()
    token = "secret-webhook-token-1234567890ab"
    await db.tenants.insert_one({"id": tid, "slug": "alpha", "name": "Alpha", "status": "active"})
    await db.users.insert_one({
        "id": uid, "tenant_id": tid, "email": "a@t.local", "password_hash": "x",
        "name": "A", "role": "admin", "status": "active",
    })
    await db.projects.insert_one({"id": pj, "tenant_id": tid, "name": "P", "status": "active"})
    await db.clients.insert_one({
        "id": cid, "tenant_id": tid, "project_id": pj, "name": "Cubbo",
        "ingest_mode": "webhook", "webhook_token": token,
    })
    return {"tenant_id": tid, "user_id": uid, "client_id": cid, "token": token}


def _payload(**over):
    base = {
        "tracking_id": "FX-001",
        "carrier_code": "fedex",
        "carrier_status": "IN_TRANSIT",
    }
    base.update(over)
    return json.dumps(base, separators=(",", ":")).encode("utf-8")


@pytest.mark.asyncio
async def test_webhook_signed_creates_guia(client, db, setup):
    body = _payload()
    r = await client.post(
        f"/api/guias/ingest/webhook?client_id={setup['client_id']}",
        content=body,
        headers={"X-MyE-Signature": sign(setup["token"], body),
                 "Content-Type": "application/json"},
    )
    assert r.status_code == 202
    assert r.json()["data"]["action"] == "created"
    assert await db.guias.count_documents({"tenant_id": setup["tenant_id"]}) == 1


@pytest.mark.asyncio
async def test_webhook_bad_signature_rejected(client, setup):
    body = _payload()
    r = await client.post(
        f"/api/guias/ingest/webhook?client_id={setup['client_id']}",
        content=body,
        headers={"X-MyE-Signature": "deadbeef", "Content-Type": "application/json"},
    )
    assert r.status_code == 401
    assert r.json()["errors"][0]["code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_webhook_update_then_terminal_then_blocked(client, db, setup):
    # 1) create
    body1 = _payload(carrier_status="IN_TRANSIT")
    await client.post(f"/api/guias/ingest/webhook?client_id={setup['client_id']}",
                      content=body1, headers={"X-MyE-Signature": sign(setup["token"], body1)})
    # 2) same status → discarded_no_change
    r2 = await client.post(f"/api/guias/ingest/webhook?client_id={setup['client_id']}",
                           content=body1, headers={"X-MyE-Signature": sign(setup["token"], body1)})
    assert r2.json()["data"]["action"] == "discarded_no_change"
    # 3) update to DELIVERED → flips terminal
    body3 = _payload(carrier_status="DELIVERED")
    r3 = await client.post(f"/api/guias/ingest/webhook?client_id={setup['client_id']}",
                           content=body3, headers={"X-MyE-Signature": sign(setup["token"], body3)})
    assert r3.json()["data"]["action"] == "updated"
    assert r3.json()["data"]["is_terminal"] is True
    # 4) any further webhook is silently dropped (R02)
    body4 = _payload(carrier_status="IN_TRANSIT_REOPEN")
    r4 = await client.post(f"/api/guias/ingest/webhook?client_id={setup['client_id']}",
                           content=body4, headers={"X-MyE-Signature": sign(setup["token"], body4)})
    assert r4.json()["data"]["action"] == "discarded_terminal"
    # And only one guía exists
    assert await db.guias.count_documents({"tenant_id": setup["tenant_id"]}) == 1
    g = await db.guias.find_one({"tenant_id": setup["tenant_id"]})
    assert g["carrier_status"] == "DELIVERED"


@pytest.mark.asyncio
async def test_layout_csv_upload(client, db, setup):
    # Iter39 — migrated to Layout v2 (headers en español).
    csv_bytes = (
        "Tracking,Courier,Status\n"
        "L-1,fedex,En tránsito\n"
        "L-2,fedex,En reparto\n"
        "L-3,fedex,Entregado\n"
    ).encode("utf-8")
    h = _bearer(user_id=setup["user_id"], tenant_id=setup["tenant_id"], role="admin")
    r = await client.post(
        f"/api/admin/ingest/layout?client_id={setup['client_id']}",
        files={"file": ("guias.csv", csv_bytes, "text/csv")},
        headers=h,
    )
    assert r.status_code == 200
    summary = r.json()["data"]["summary"]
    assert summary["created"] == 3
    assert summary["rows"] == 3
    # The DELIVERED one should be terminal
    g = await db.guias.find_one({"tenant_id": setup["tenant_id"], "tracking_id": "L-3"})
    assert g["is_terminal"] is True


@pytest.mark.asyncio
async def test_layout_rejects_non_csv(client, setup):
    h = _bearer(user_id=setup["user_id"], tenant_id=setup["tenant_id"], role="admin")
    r = await client.post(
        f"/api/admin/ingest/layout?client_id={setup['client_id']}",
        files={"file": ("guias.txt", b"hello", "text/plain")},
        headers=h,
    )
    assert r.status_code == 422
    assert r.json()["errors"][0]["code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_admin_pull_returns_metadata_no_secrets(client, setup):
    h = _bearer(user_id=setup["user_id"], tenant_id=setup["tenant_id"], role="admin")
    r = await client.post(f"/api/admin/ingest/pull/{setup['client_id']}", headers=h)
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["client_id"] == setup["client_id"]
    assert body["ingest_mode"] == "webhook"
    assert "api_creds_ref" not in body
    assert "webhook_token" not in body
