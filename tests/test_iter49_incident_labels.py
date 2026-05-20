"""Iter49 · incident_type → label legible en español.

Cubre:
  - `services.incident_labels.label_for()` mapping unit tests
  - `enrich_incident_label()` agrega `incident_type_label` in-place
  - `GET /api/agent/queue` devuelve tickets con `incident_type_label`
  - `GET /api/agent/tickets/{id}` devuelve ticket con `incident_type_label`
  - Tickets con incident_type=null no rompen ni añaden la key
"""
from __future__ import annotations
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token, hash_password
from core.uuid import new_id
from services.incident_labels import (
    INCIDENT_TYPE_LABELS_ES,
    label_for,
    resolve_incident_label,
    enrich_incident_label,
    enrich_incident_label_many,
)


def _bearer(*, user_id: str, tenant_id: str, role: str = "agent",
            email: str = "agent@t.io"):
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
    agent_id = new_id()
    pwd = hash_password("x")
    await db.tenants.insert_one(
        {"id": t_id, "slug": "t-l", "name": "T-L", "status": "active"})
    await db.users.insert_one({
        "id": agent_id, "tenant_id": t_id,
        "email": "agent@t-l.io", "role": "agent",
        "name": "Agente Uno",
        "password_hash": pwd, "status": "active",
    })
    return {"tenant_id": t_id, "agent_id": agent_id}


# ─────────────────────────── Unit tests ─────────────────────────────
class TestLabelMapping:
    def test_known_keys_have_spanish_label(self):
        # Smoke: todas las keys conocidas devuelven label distinto a la key.
        for k in ["address_issue", "refused", "customs", "damage", "lost",
                  "failed", "returned", "exception", "other"]:
            assert k in INCIDENT_TYPE_LABELS_ES, f"missing label for {k}"
            assert INCIDENT_TYPE_LABELS_ES[k] != k

    def test_label_for_exception_returns_legible(self):
        # Caso central del bug: "exception" NO debe quedar como string raw.
        assert label_for("exception") == "Incidencia genérica"

    def test_label_for_refused_is_rechazo(self):
        # El issue del usuario menciona "Rechazo" como ejemplo.
        assert label_for("refused") == "Rechazo del destinatario"

    def test_label_for_none_returns_none(self):
        assert label_for(None) is None
        assert label_for("") is None

    def test_label_for_unknown_returns_self(self):
        # No conocemos la key → devolvemos la key sin transformar
        # (mejor que romper el front).
        assert label_for("bogus_xyz") == "bogus_xyz"


class TestEnrich:
    def test_enrich_adds_label_in_place(self):
        d = {"id": "abc", "incident_type": "refused"}
        out = enrich_incident_label(d)
        assert out is d  # in-place
        assert d["incident_type_label"] == "Rechazo del destinatario"
        assert d["incident_label"] == "Rechazo del destinatario"

    def test_enrich_handles_none(self):
        assert enrich_incident_label(None) is None

    def test_enrich_skips_when_no_incident_type(self):
        d = {"id": "abc"}
        enrich_incident_label(d)
        assert "incident_type_label" not in d
        assert "incident_label" not in d

    def test_enrich_prefers_carrier_incidence(self):
        # JERARQUÍA: si la guía tiene `carrier_incidence` específico, éste
        # tiene precedencia sobre el genérico "Incidencia genérica".
        d = {"id": "x", "incident_type": "exception"}
        enrich_incident_label(d, carrier_incidence="Rechazo")
        assert d["incident_type_label"] == "Incidencia genérica"  # del enum
        assert d["incident_label"] == "Rechazo"  # del adapter, prioritario

    def test_resolve_helper_jerarquia(self):
        assert resolve_incident_label("exception", "Rechazo") == "Rechazo"
        assert resolve_incident_label("refused", None) == "Rechazo del destinatario"
        assert resolve_incident_label(None, None) is None
        assert resolve_incident_label(None, "Custom") == "Custom"

    def test_enrich_many_processes_list_with_carrier_map(self):
        items = [
            {"id": "a", "guia_id": "g1", "incident_type": "exception"},
            {"id": "b", "guia_id": "g2", "incident_type": "damage"},
            {"id": "c", "incident_type": "exception"},  # sin guia
        ]
        cmap = {"g1": "Rechazo del destinatario"}
        enrich_incident_label_many(items, carrier_incidence_by_guia=cmap)
        assert items[0]["incident_label"] == "Rechazo del destinatario"  # mapa
        assert items[1]["incident_label"] == "Mercancía dañada"  # fallback enum
        assert items[2]["incident_label"] == "Incidencia genérica"  # fallback enum


# ─────────────────────────── REST API ─────────────────────────────
@pytest.mark.asyncio
class TestAgentQueueLabel:
    async def test_queue_returns_incident_label_from_guia(
            self, db, env, http_client):
        """Caso central del bug del usuario: la guía tiene `carrier_incidence`
        específica ("Rechazo") y el ticket tiene `incident_type="exception"`
        genérico. El header debe mostrar "Rechazo", no "Incidencia genérica".

        Iter51 — además, el ticket debe quedar enriquecido con `carrier_code`
        desde la guía (la vista Tabla mostraba `carrier_status_raw` por error).
        """
        now = datetime.now(timezone.utc).isoformat()
        t_id = env["tenant_id"]
        a_id = env["agent_id"]
        guia_id = new_id()
        ticket_id = new_id()
        await db.guias.insert_one({
            "id": guia_id, "tenant_id": t_id,
            "tracking_id": "TRK-1", "carrier_code": "fedex",
            "carrier_incidence": "Rechazo",
            "created_at": now, "updated_at": now,
        })
        await db.tickets.insert_one({
            "id": ticket_id, "tenant_id": t_id, "guia_id": guia_id,
            "client_id": None, "status": "pending",
            "incident_type": "exception",  # genérico — debe ser sobreescrito
            "motivo_id": None, "assigned_agent_id": a_id,
            "carrier_status_raw": "EXCEPTION",
            # carrier_code NO está en el ticket — debe venir de la guía
            "tracking_id": "TRK-1", "created_at": now, "updated_at": now,
        })
        headers = _bearer(user_id=a_id, tenant_id=t_id)
        r = await http_client.get("/api/agent/queue", headers=headers)
        assert r.status_code == 200, r.text
        mine = r.json()["data"]["mine"]
        assert len(mine) == 1
        assert mine[0]["incident_type"] == "exception"
        assert mine[0]["incident_type_label"] == "Incidencia genérica"
        # Lo que el frontend renderiza:
        assert mine[0]["incident_label"] == "Rechazo"
        # Iter51 — carrier_code enriquecido desde la guía
        assert mine[0]["carrier_code"] == "fedex"

    async def test_queue_returns_enum_label_when_no_guia(
            self, db, env, http_client):
        """Cuando no hay guía o no tiene `carrier_incidence`, se cae al label
        español del enum (`exception` → "Incidencia genérica")."""
        now = datetime.now(timezone.utc).isoformat()
        t_id = env["tenant_id"]
        a_id = env["agent_id"]
        await db.tickets.insert_one({
            "id": new_id(), "tenant_id": t_id, "guia_id": None,
            "status": "pending", "incident_type": "refused",
            "assigned_agent_id": a_id, "tracking_id": "TRK-2",
            "created_at": now, "updated_at": now,
        })
        headers = _bearer(user_id=a_id, tenant_id=t_id)
        r = await http_client.get("/api/agent/queue", headers=headers)
        assert r.status_code == 200, r.text
        mine = r.json()["data"]["mine"]
        assert len(mine) == 1
        assert mine[0]["incident_label"] == "Rechazo del destinatario"

    async def test_queue_skips_label_when_no_incident_type(
            self, db, env, http_client):
        now = datetime.now(timezone.utc).isoformat()
        t_id = env["tenant_id"]
        a_id = env["agent_id"]
        await db.tickets.insert_one({
            "id": new_id(), "tenant_id": t_id, "status": "pending",
            "incident_type": None,
            "assigned_agent_id": a_id, "tracking_id": "TRK-3",
            "created_at": now, "updated_at": now,
        })
        headers = _bearer(user_id=a_id, tenant_id=t_id)
        r = await http_client.get("/api/agent/queue", headers=headers)
        assert r.status_code == 200, r.text
        mine = r.json()["data"]["mine"]
        assert len(mine) == 1
        # No debe explotar; tampoco poner la key cuando incident_type es None.
        assert mine[0].get("incident_type_label") is None
        assert mine[0].get("incident_label") is None


@pytest.mark.asyncio
class TestAgentDetailLabel:
    async def test_detail_prefers_carrier_incidence_from_guia(
            self, db, env, http_client):
        """En la vista de detalle, si la guía linked tiene `carrier_incidence`,
        el ticket debe exponer ese valor como `incident_label`."""
        now = datetime.now(timezone.utc).isoformat()
        t_id = env["tenant_id"]
        a_id = env["agent_id"]
        guia_id = new_id()
        ticket_id = new_id()
        await db.guias.insert_one({
            "id": guia_id, "tenant_id": t_id,
            "tracking_id": "TRK-X", "carrier_code": "fedex",
            "carrier_incidence": "Domicilio no localizado",
            "created_at": now, "updated_at": now,
        })
        await db.tickets.insert_one({
            "id": ticket_id, "tenant_id": t_id, "guia_id": guia_id,
            "client_id": None, "status": "pending",
            "incident_type": "exception",
            "assigned_agent_id": a_id, "tracking_id": "TRK-X",
            "created_at": now, "updated_at": now,
        })
        headers = _bearer(user_id=a_id, tenant_id=t_id)
        r = await http_client.get(
            f"/api/agent/tickets/{ticket_id}", headers=headers)
        assert r.status_code == 200, r.text
        ticket = r.json()["data"]["ticket"]
        assert ticket["incident_type"] == "exception"
        assert ticket["incident_type_label"] == "Incidencia genérica"
        # Frontend renderiza este:
        assert ticket["incident_label"] == "Domicilio no localizado"

    async def test_detail_fallbacks_to_enum_label(
            self, db, env, http_client):
        now = datetime.now(timezone.utc).isoformat()
        t_id = env["tenant_id"]
        a_id = env["agent_id"]
        ticket_id = new_id()
        await db.tickets.insert_one({
            "id": ticket_id, "tenant_id": t_id, "guia_id": None,
            "status": "pending", "incident_type": "exception",
            "assigned_agent_id": a_id, "tracking_id": "TRK-Y",
            "created_at": now, "updated_at": now,
        })
        headers = _bearer(user_id=a_id, tenant_id=t_id)
        r = await http_client.get(
            f"/api/agent/tickets/{ticket_id}", headers=headers)
        assert r.status_code == 200, r.text
        ticket = r.json()["data"]["ticket"]
        assert ticket["incident_label"] == "Incidencia genérica"
