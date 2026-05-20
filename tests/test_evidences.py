"""PROMPT 11.6 — Evidencias (foto/PDF + coords + Leaflet/OSM).

Cobertura:
  * Upload con ticket_id válido → 201 + doc.id; archivo persiste en disco.
  * Upload con claim_id terminal → 409.
  * Upload sin ticket ni claim → 422.
  * Upload con MIME no permitido → 422.
  * GET /file devuelve el binario al uploader y a otros agentes del tenant.
  * Cross-tenant GET /file → 404.
  * DELETE: uploader puede borrar; otro agente no; admin sí; archivo se borra.
  * Bloqueo de delete cuando la evidencia es referenciada por expediente activo.
"""
from __future__ import annotations
from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport

from server import app
from core.security import create_access_token
from core.uuid import new_id


def _bearer(*, user_id, tenant_id, role="agent", email="ag@t"):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_id, tenant_id=tenant_id, role=role, email=email)}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def ev_setup(db, tmp_path, monkeypatch):
    """Tenant + agent + admin + ticket + claim listo para anclar evidencia."""
    # Aisla disco a tmp_path para que el test no toque /app/data/evidences real
    from pathlib import Path as _P
    from repositories import evidences as ev_mod
    monkeypatch.setattr(ev_mod, "EVIDENCE_ROOT", _P(str(tmp_path / "ev")))
    monkeypatch.setenv("CRON_ENABLED", "0")

    tid, uid_agent, uid_other, uid_admin = new_id(), new_id(), new_id(), new_id()
    pj_id, cl_id, guia_id, ticket_id, claim_id = (new_id() for _ in range(5))
    await db.tenants.insert_one({"id": tid, "slug": "ev", "name": "Ev", "status": "active"})
    await db.users.insert_many([
        {"id": uid_agent, "tenant_id": tid, "email": "ag@t",
         "password_hash": "x", "name": "Agente", "role": "agent", "status": "active"},
        {"id": uid_other, "tenant_id": tid, "email": "ot@t",
         "password_hash": "x", "name": "Otro", "role": "agent", "status": "active"},
        {"id": uid_admin, "tenant_id": tid, "email": "ad@t",
         "password_hash": "x", "name": "Admin", "role": "admin", "status": "active"},
    ])
    await db.projects.insert_one({"id": pj_id, "tenant_id": tid, "name": "P", "status": "active"})
    await db.clients.insert_one({
        "id": cl_id, "tenant_id": tid, "project_id": pj_id, "name": "C",
        "ingest_mode": "webhook", "webhook_token": "x",
    })
    await db.guias.insert_one({
        "id": guia_id, "tenant_id": tid, "tracking_id": "T1",
        "carrier_id": "fedex", "client_id": cl_id,
        "carrier_status": "delivered", "internal_status": "delivered",
        "is_terminal": True,
    })
    await db.tickets.insert_one({
        "id": ticket_id, "tenant_id": tid, "client_id": cl_id, "guia_id": guia_id,
        "status": "in_progress", "assigned_agent_id": uid_agent,
        "incident_type": "damage", "canonical_status": "exception",
        "carrier_status_raw": "DM", "source": "ingest",
        "created_at": "2026-05-01T00:00:00Z", "updated_at": "2026-05-01T00:00:00Z",
    })
    await db.claims.insert_one({
        "id": claim_id, "tenant_id": tid, "ticket_id": ticket_id, "client_id": cl_id,
        "estado": "promovido", "is_terminal": False,
        "tipo_dano": "dano_total", "monto_reclamado": 100, "divisa": "MXN",
        "promoted_by": uid_agent, "promoted_at": "2026-05-01T00:00:00Z",
        "expediente": {}, "created_at": "2026-05-01T00:00:00Z", "updated_at": "2026-05-01T00:00:00Z",
    })
    return {
        "tenant_id": tid, "agent_id": uid_agent, "other_id": uid_other,
        "admin_id": uid_admin, "ticket_id": ticket_id, "claim_id": claim_id,
        "tmp_root": tmp_path / "ev",
    }


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xc8\xb1\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ───────────────────────── Upload ─────────────────────────────────────
@pytest.mark.asyncio
async def test_upload_to_ticket_persists_file_and_timeline(http_client, db, ev_setup):
    s = ev_setup
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    files = {"file": ("photo.png", PNG_BYTES, "image/png")}
    data = {"ticket_id": s["ticket_id"], "lat": "19.43", "lng": "-99.13",
            "location_label": "CDMX centro", "note": "paquete dañado"}
    r = await http_client.post("/api/evidencias/upload", headers=h, data=data, files=files)
    assert r.status_code == 201, r.text
    ev = r.json()["data"]
    assert ev["id"] and ev["mime"] == "image/png"
    assert ev["lat"] == 19.43 and ev["lng"] == -99.13
    assert "file_path" not in ev  # nunca se expone

    # Archivo escrito a disco
    saved = await db.evidences.find_one({"id": ev["id"]})
    assert saved and Path(saved["file_path"]).exists()
    # Timeline mirror
    tl = await db.timeline_events.find_one({
        "tenant_id": s["tenant_id"], "ticket_id": s["ticket_id"],
        "event_type": "evidence_added",
    })
    assert tl and tl["payload"]["evidence_id"] == ev["id"]


@pytest.mark.asyncio
async def test_upload_to_claim_records_event(http_client, db, ev_setup):
    s = ev_setup
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.post(
        "/api/evidencias/upload", headers=h,
        data={"claim_id": s["claim_id"]},
        files={"file": ("doc.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert r.status_code == 201
    ev = r.json()["data"]
    assert ev["claim_id"] == s["claim_id"] and ev["kind"] == "document"
    cev = await db.claim_events.find_one({"claim_id": s["claim_id"], "event_type": "evidence_added"})
    assert cev


@pytest.mark.asyncio
async def test_upload_terminal_claim_blocked(http_client, db, ev_setup):
    s = ev_setup
    await db.claims.update_one({"id": s["claim_id"]},
        {"$set": {"estado": "desistido", "is_terminal": True}})
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.post(
        "/api/evidencias/upload", headers=h,
        data={"claim_id": s["claim_id"]},
        files={"file": ("x.png", PNG_BYTES, "image/png")},
    )
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "TERMINAL_STATE"


@pytest.mark.asyncio
async def test_upload_requires_anchor(http_client, ev_setup):
    s = ev_setup
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.post(
        "/api/evidencias/upload", headers=h, data={},
        files={"file": ("x.png", PNG_BYTES, "image/png")},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_upload_rejects_bad_mime(http_client, ev_setup):
    s = ev_setup
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    r = await http_client.post(
        "/api/evidencias/upload", headers=h,
        data={"ticket_id": s["ticket_id"]},
        files={"file": ("malware.exe", b"MZ\x90", "application/x-msdownload")},
    )
    assert r.status_code == 422


# ───────────────────────── List + serve ───────────────────────────────
@pytest.mark.asyncio
async def test_list_and_serve_file(http_client, ev_setup):
    s = ev_setup
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    up = await http_client.post(
        "/api/evidencias/upload", headers=h,
        data={"ticket_id": s["ticket_id"]},
        files={"file": ("p.png", PNG_BYTES, "image/png")},
    )
    eid = up.json()["data"]["id"]
    # List
    rl = await http_client.get(f"/api/evidencias?ticket_id={s['ticket_id']}", headers=h)
    items = rl.json()["data"]["items"]
    assert any(it["id"] == eid for it in items)
    assert all("file_path" not in it for it in items)
    # Serve
    rf = await http_client.get(f"/api/evidencias/{eid}/file", headers=h)
    assert rf.status_code == 200
    assert rf.headers["content-type"] == "image/png"
    assert rf.content == PNG_BYTES


# ───────────────────────── DELETE rules ───────────────────────────────
@pytest.mark.asyncio
async def test_delete_uploader_only_or_admin(http_client, db, ev_setup):
    s = ev_setup
    h_agent = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    up = await http_client.post(
        "/api/evidencias/upload", headers=h_agent,
        data={"ticket_id": s["ticket_id"]},
        files={"file": ("p.png", PNG_BYTES, "image/png")},
    )
    eid = up.json()["data"]["id"]
    # Otro agente del mismo tenant NO puede borrar
    h_other = _bearer(user_id=s["other_id"], tenant_id=s["tenant_id"], role="agent")
    r1 = await http_client.delete(f"/api/evidencias/{eid}", headers=h_other)
    assert r1.status_code == 403
    # Admin sí puede
    h_admin = _bearer(user_id=s["admin_id"], tenant_id=s["tenant_id"], role="admin")
    r2 = await http_client.delete(f"/api/evidencias/{eid}", headers=h_admin)
    assert r2.status_code == 200
    # File should be gone from disk
    saved = await db.evidences.find_one({"id": eid})
    assert saved is None


@pytest.mark.asyncio
async def test_delete_blocked_when_in_active_expediente(http_client, db, ev_setup):
    s = ev_setup
    h = _bearer(user_id=s["agent_id"], tenant_id=s["tenant_id"], role="agent")
    up = await http_client.post(
        "/api/evidencias/upload", headers=h,
        data={"claim_id": s["claim_id"]},
        files={"file": ("p.png", PNG_BYTES, "image/png")},
    )
    eid = up.json()["data"]["id"]
    # Atar al expediente activo
    await db.claims.update_one({"id": s["claim_id"]},
        {"$set": {"expediente.evidencia_ids": [eid]}})
    r = await http_client.delete(f"/api/evidencias/{eid}", headers=h)
    assert r.status_code == 409
    assert r.json()["errors"][0]["code"] == "TERMINAL_STATE"
