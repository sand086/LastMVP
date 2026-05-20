"""PROMPT 11.6 — Cross-tenant isolation explicit coverage.

Validates that an evidence uploaded by tenant A is invisible (404) to tenant B
on list, file serve and delete.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from server import app
from core.security import create_access_token
from core.uuid import new_id


def _bearer(*, user_id, tenant_id, role="agent", email="x@t"):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_id, tenant_id=tenant_id, role=role, email=email)}"}


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xc8\xb1\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def two_tenants(db, tmp_path, monkeypatch):
    from pathlib import Path as _P
    from repositories import evidences as ev_mod
    monkeypatch.setattr(ev_mod, "EVIDENCE_ROOT", _P(str(tmp_path / "ev")))
    monkeypatch.setenv("CRON_ENABLED", "0")

    tA, tB = new_id(), new_id()
    uA, uB = new_id(), new_id()
    pj, cl, guia, ticket = new_id(), new_id(), new_id(), new_id()
    await db.tenants.insert_many([
        {"id": tA, "slug": "ta", "name": "TA", "status": "active"},
        {"id": tB, "slug": "tb", "name": "TB", "status": "active"},
    ])
    await db.users.insert_many([
        {"id": uA, "tenant_id": tA, "email": "a@t", "password_hash": "x",
         "name": "A", "role": "agent", "status": "active"},
        {"id": uB, "tenant_id": tB, "email": "b@t", "password_hash": "x",
         "name": "B", "role": "agent", "status": "active"},
    ])
    await db.projects.insert_one({"id": pj, "tenant_id": tA, "name": "P", "status": "active"})
    await db.clients.insert_one({"id": cl, "tenant_id": tA, "project_id": pj,
                                 "name": "C", "ingest_mode": "webhook", "webhook_token": "x"})
    await db.guias.insert_one({"id": guia, "tenant_id": tA, "tracking_id": "T",
                               "carrier_id": "fedex", "client_id": cl,
                               "carrier_status": "delivered",
                               "internal_status": "delivered", "is_terminal": True})
    await db.tickets.insert_one({"id": ticket, "tenant_id": tA, "client_id": cl,
                                 "guia_id": guia, "status": "in_progress",
                                 "assigned_agent_id": uA,
                                 "incident_type": "damage",
                                 "canonical_status": "exception",
                                 "carrier_status_raw": "DM", "source": "ingest",
                                 "created_at": "2026-05-01T00:00:00Z",
                                 "updated_at": "2026-05-01T00:00:00Z"})
    return {"tA": tA, "tB": tB, "uA": uA, "uB": uB, "ticket_id": ticket}


@pytest.mark.asyncio
async def test_cross_tenant_evidence_invisible(http_client, two_tenants):
    s = two_tenants
    hA = _bearer(user_id=s["uA"], tenant_id=s["tA"], role="agent")
    hB = _bearer(user_id=s["uB"], tenant_id=s["tB"], role="agent")

    # Tenant A uploads
    up = await http_client.post(
        "/api/evidencias/upload", headers=hA,
        data={"ticket_id": s["ticket_id"]},
        files={"file": ("p.png", PNG_BYTES, "image/png")},
    )
    assert up.status_code == 201, up.text
    eid = up.json()["data"]["id"]

    # Tenant B list by ticket_id of tenant A → empty (NOT 200 with the item)
    rl = await http_client.get(f"/api/evidencias?ticket_id={s['ticket_id']}", headers=hB)
    assert rl.status_code == 200
    items = rl.json()["data"]["items"]
    assert all(it["id"] != eid for it in items), f"Tenant B leaked items: {items}"
    assert items == [] or len(items) == 0

    # Tenant B cannot fetch the file
    rf = await http_client.get(f"/api/evidencias/{eid}/file", headers=hB)
    assert rf.status_code == 404, f"got {rf.status_code} — cross-tenant file leak!"

    # Tenant B cannot delete
    rd = await http_client.delete(f"/api/evidencias/{eid}", headers=hB)
    assert rd.status_code == 404, f"got {rd.status_code} — cross-tenant delete leak!"

    # Tenant A still sees it
    rA = await http_client.get(f"/api/evidencias?ticket_id={s['ticket_id']}", headers=hA)
    assert any(it["id"] == eid for it in rA.json()["data"]["items"])
