"""Iter61 · Enriquecimiento de tickets con reports del driver de Routal.

Cubre:
  - Adapter `_extract_first_report` parsea correctamente la estructura real
    de un report de Routal (id, type, comments, custom_fields.motivos_de_
    cancelacion.label, images).
  - `_stop_to_event` incluye `routal_report` en raw_payload cuando aplica.
  - `process_event` propaga `routal_report` a `carrier_meta` y rellena
    `carrier_incidence` cuando viene vacío.
  - `WorkflowEngine.process_post_ingest` crea ticket con
    `incident_subtype` y `carrier_incident_detail` cuando hay report.
  - Endpoint backfill `POST /admin/routal/enrich-reports` actualiza guías
    + tickets existentes.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id
from services.cae.adapters.routal import _extract_first_report, RoutalAdapter
from services.ingest_service import IngestService


def _bearer(*, user_id, tenant_id, role="admin", email="u@t.io"):
    tok = create_access_token(
        user_id=user_id, tenant_id=tenant_id, role=role, email=email)
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        yield ac


SAMPLE_REPORT = {
    "id": "rep-1",
    "stop_id": "stop-1",
    "type": "service_report_canceled",
    "comments": "  No salió nadie del domicilio  ",
    "created_at": "2026-05-14T19:25:57.395Z",
    "driver_id": "driver-1",
    "custom_fields": {
        "motivos_de_cancelacion": {"id": 0, "label": "Destinatario ausente"},
    },
    "images": [
        {"id": "im-1", "url": "https://api.routal.com/v3/.../im-1"},
        {"id": "im-2", "url": "https://api.routal.com/v3/.../im-2"},
    ],
    "location": {"lat": 25.7, "lng": -100.2},
}


def test_extract_first_report_basic():
    stop = {"id": "stop-1", "status": "canceled", "reports": [SAMPLE_REPORT]}
    r = _extract_first_report(stop)
    assert r is not None
    assert r["report_id"] == "rep-1"
    assert r["report_type"] == "service_report_canceled"
    assert r["comments"] == "No salió nadie del domicilio"  # stripped
    assert r["reason_label"] == "Destinatario ausente"
    assert r["images_count"] == 2
    assert len(r["images"]) == 2
    assert r["images"][0]["url"].endswith("im-1")


def test_extract_first_report_no_reports():
    assert _extract_first_report({"reports": []}) is None
    assert _extract_first_report({}) is None


def test_extract_first_report_no_custom_field():
    stop = {"reports": [{
        "id": "x", "type": "service_report_completed",
        "comments": "ok", "custom_fields": {}, "images": [],
    }]}
    r = _extract_first_report(stop)
    assert r["reason_label"] is None


def test_stop_to_event_includes_routal_report():
    adapter = RoutalAdapter(api_key="K" * 30, project_ids=["p"])
    stop = {
        "id": "stop-1", "status": "canceled",
        "external_id": "TRK-1", "plan_id": "plan-1",
        "location": {"lat": 1, "lng": 2},
        "reports": [SAMPLE_REPORT],
    }
    ev = adapter._stop_to_event("TRK-1", stop)
    assert ev.raw_code == "canceled"
    assert ev.raw_payload["reports_count"] == 1
    assert ev.raw_payload["routal_report"]["reason_label"] == \
        "Destinatario ausente"


@pytest.fixture
async def env(db):
    t_id = new_id()
    admin_id = new_id()
    client_id = new_id()
    entry_id = new_id()
    await db.tenants.insert_one(
        {"id": t_id, "slug": "t-61", "name": "T-61", "status": "active"})
    await db.users.insert_one({
        "id": admin_id, "tenant_id": t_id, "email": "ad@t-61.io",
        "role": "admin", "password_hash": "x", "status": "active",
    })
    await db.clients.insert_one({
        "id": client_id, "tenant_id": t_id, "name": "Cli T61",
        "slug": "cli-t61", "status": "active",
    })
    await db.carriers.insert_one({
        "id": new_id(), "tenant_id": t_id, "code": "routal",
        "name": "Routal", "status": "active",
    })
    await db.carrier_status_catalog.insert_one({
        "id": entry_id, "tenant_id": None,
        "carrier_id": "routal", "raw_code": "canceled",
        "api_version": "v2", "canonical_status": "exception",
        "incident_type": None, "is_terminal": False,
        "requires_action": True, "display_label_es": "Cancelado",
        "confidence": 100, "active": True, "source": "anchor_seed",
    })
    return {"tenant_id": t_id, "admin_id": admin_id,
            "client_id": client_id, "entry_id": entry_id}


@pytest.mark.asyncio
async def test_ingest_persists_routal_report_and_creates_enriched_ticket(db, env):
    svc = IngestService(tenant_id=env["tenant_id"])
    raw_payload = {
        "stop_id": "stop-1", "plan_id": "plan-1",
        "routal_report": {
            "report_id": "rep-1",
            "report_type": "service_report_canceled",
            "comments": "Cliente rechazó el paquete",
            "reason_label": "Rechazado por cliente",
            "images_count": 1,
            "images": [{"id": "im-1", "url": "https://x/im-1"}],
            "report_at": "2026-05-14T20:00:00Z",
        },
    }
    out = await svc.process_event(
        client_id=env["client_id"], tracking_id="TRK-ENR-1",
        carrier_code="routal", carrier_status="canceled",
        raw_code="canceled", api_version="v2",
        raw_payload=raw_payload, source="pull",
    )
    assert out.action == "created"
    guia = await db.guias.find_one({"tracking_id": "TRK-ENR-1"}, {"_id": 0})
    # carrier_meta.routal_report persistido
    assert guia["carrier_meta"]["routal_report"]["report_id"] == "rep-1"
    # carrier_incidence rellenado con reason_label
    assert guia["carrier_incidence"] == "Rechazado por cliente"

    ticket = await db.tickets.find_one(
        {"guia_id": guia["id"]}, {"_id": 0})
    assert ticket is not None
    assert ticket["incident_subtype"] == "Rechazado por cliente"
    # incident_type también enriquecido (no genérico "exception")
    assert ticket["incident_type"] == "Rechazado por cliente"
    detail = ticket["carrier_incident_detail"]
    assert detail["report_id"] == "rep-1"
    assert detail["comments"] == "Cliente rechazó el paquete"
    assert detail["images_count"] == 1


@pytest.mark.asyncio
async def test_enrich_endpoint_validates_credentials(http_client, db, env):
    # Sin platform_carrier_configs ni cliente.carriers.routal.api_key_ref →
    # missing_credentials.
    h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"])
    r = await http_client.post(
        "/api/admin/routal/enrich-reports", headers=h,
        json={"client_id": env["client_id"], "raw_code": "canceled"})
    assert r.status_code == 200
    assert r.json()["data"]["result"] == "missing_credentials"


@pytest.mark.asyncio
async def test_enrich_endpoint_client_not_found(http_client, env):
    h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"])
    r = await http_client.post(
        "/api/admin/routal/enrich-reports", headers=h,
        json={"client_id": "does-not-exist", "raw_code": "canceled"})
    assert r.status_code == 404
