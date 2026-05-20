"""Iter62 · Sintetizar recipient desde raw_payload (caso Routal pull).

Cuando el cliente ingesta vía pull/webhook sin Layout V2, no hay
``guia.recipient`` para que la UI agente muestre destinatario+contacto.
Este test cubre el helper que sintetiza recipient desde raw_payload
(label, location, phone, email).
"""
from __future__ import annotations

import pytest

from services.ingest_service import (
    IngestService, _synthesize_recipient_from_raw_payload,
)
from core.uuid import new_id


def test_synthesize_from_routal_label_with_tracking_suffix():
    rp = {
        "label": "David Anta Guerrero - z1RzcbMtV3udhyqe",
        "location": {"address": "peralvillo Rio consulado 1379",
                     "city": "CIUDAD DE MEXICO", "state": "CDMX",
                     "postal_code": "06220", "country_code": "MX",
                     "lat": 19.46, "lng": -99.13},
        "phone": "5580207991",
        "email": "davidanta24@gmail.com",
    }
    r = _synthesize_recipient_from_raw_payload(rp)
    assert r["name"] == "David Anta Guerrero"
    assert r["address"] == "peralvillo Rio consulado 1379"
    assert r["city"] == "CIUDAD DE MEXICO"
    assert r["cp"] == "06220"
    assert r["phone"] == "5580207991"
    assert r["email"] == "davidanta24@gmail.com"
    assert r["lat"] == 19.46


def test_synthesize_with_full_address_prefers_label():
    rp = {
        "label": "Cliente X",
        "location": {"label": "Calle 1 #2, Col Centro, CDMX",
                     "address": "Calle 1 #2"},
        "phone": None, "email": None,
    }
    r = _synthesize_recipient_from_raw_payload(rp)
    # full_address (loc.label) preferido cuando existe
    assert r["address"] == "Calle 1 #2, Col Centro, CDMX" or \
           r["address"] == "Calle 1 #2"


def test_synthesize_empty():
    assert _synthesize_recipient_from_raw_payload({}) is None
    assert _synthesize_recipient_from_raw_payload({"foo": "bar"}) is None


@pytest.fixture
async def env(db):
    t_id = new_id()
    client_id = new_id()
    await db.tenants.insert_one(
        {"id": t_id, "slug": "t-62", "name": "T-62", "status": "active"})
    await db.clients.insert_one({
        "id": client_id, "tenant_id": t_id, "name": "Cli T62",
        "slug": "cli-t62", "status": "active",
    })
    await db.carriers.insert_one({
        "id": new_id(), "tenant_id": t_id, "code": "routal",
        "name": "Routal", "status": "active",
    })
    return {"tenant_id": t_id, "client_id": client_id}


@pytest.mark.asyncio
async def test_ingest_synthesizes_recipient_when_not_provided(db, env):
    svc = IngestService(tenant_id=env["tenant_id"])
    raw_payload = {
        "label": "Juan Perez - ABC123",
        "location": {"address": "Av Reforma 100", "city": "CDMX",
                     "state": "CDMX", "postal_code": "06600",
                     "country_code": "MX", "lat": 19.4, "lng": -99.16},
        "phone": "5555555555", "email": "juan@test.io",
    }
    out = await svc.process_event(
        client_id=env["client_id"], tracking_id="TRK-RCP-1",
        carrier_code="routal", carrier_status="pending",
        raw_code="pending", api_version="v2",
        raw_payload=raw_payload, source="pull",
    )
    assert out.action == "created"
    g = await db.guias.find_one({"tracking_id": "TRK-RCP-1"}, {"_id": 0})
    r = g.get("recipient") or {}
    assert r.get("name") == "Juan Perez"
    assert r.get("address") == "Av Reforma 100"
    assert r.get("phone") == "5555555555"
    assert r.get("email") == "juan@test.io"


@pytest.mark.asyncio
async def test_ingest_does_not_overwrite_explicit_recipient(db, env):
    svc = IngestService(tenant_id=env["tenant_id"])
    explicit = {"name": "Layout V2 Nombre",
                "address": "Direccion del CSV", "phone": "111"}
    out = await svc.process_event(
        client_id=env["client_id"], tracking_id="TRK-RCP-2",
        carrier_code="routal", carrier_status="pending",
        raw_code="pending", api_version="v2",
        raw_payload={"label": "Otro Nombre - X", "phone": "999"},
        recipient=explicit, source="layout",
    )
    g = await db.guias.find_one({"tracking_id": "TRK-RCP-2"}, {"_id": 0})
    assert g["recipient"]["name"] == "Layout V2 Nombre"
    assert g["recipient"]["phone"] == "111"
