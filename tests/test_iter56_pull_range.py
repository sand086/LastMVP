"""Iter56 · Pull de servicios por rango de fechas — Routal.

Cubre:
  - `RoutalAdapter.list_recent_plans` filtra localmente por `created_from`/`created_to`
  - `IngestService.trigger_pull` con date_from/date_to invoca `_pull_range`
  - `_pull_range` recorre planes → stops → process_event (idempotente)
  - Endpoint `POST /api/admin/ingest/pull/{client_id}` con body de rango
  - Carrier no soportado devuelve mensaje claro
  - Sin credenciales devuelve `no_credentials`
  - Idempotencia: 2do pull al mismo rango NO duplica guías
"""
from __future__ import annotations
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token, hash_password
from core.uuid import new_id
from services.cae.adapters.routal import RoutalAdapter
from services.ingest_service import IngestService


def _bearer(*, user_id, tenant_id, role="superadmin", email="su@t.io"):
    tok = create_access_token(
        user_id=user_id, tenant_id=tenant_id, role=role, email=email)
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def env(db):
    t_id = new_id()
    su_id = new_id()
    cli_id = new_id()
    pwd = hash_password("x")
    await db.tenants.insert_one(
        {"id": t_id, "slug": "t-56", "name": "T-56", "status": "active"})
    await db.users.insert_one(
        {"id": su_id, "tenant_id": t_id, "email": "su@t-56.io",
         "role": "superadmin", "password_hash": pwd, "status": "active"})
    await db.clients.insert_one({
        "id": cli_id, "tenant_id": t_id, "name": "Routal Cli",
        "slug": "cli-56", "ingest_mode": "pulling",
        "carrier": "routal", "api_creds_ref": "encrypted-stub",
        "api_url": "https://api.routal.com",
        "pulling_freq_min": 15,
        "routal": {
            "project_ids": ["proj-1"],
            "default_project_id": "proj-1",
        },
    })
    return {"tenant_id": t_id, "superadmin_id": su_id, "client_id": cli_id}


# ─────────────────── Adapter range filter ─────────────────────────
@pytest.mark.asyncio
class TestRoutalListPlansRange:
    async def test_filters_by_created_from(self):
        plans_response = {
            "docs": [
                {"_id": "p1", "created_at": "2026-05-10T10:00:00Z"},
                {"_id": "p2", "created_at": "2026-05-12T10:00:00Z"},
                {"_id": "p3", "created_at": "2026-05-14T10:00:00Z"},
            ]
        }

        class FakeResp:
            status_code = 200
            def json(self): return plans_response

        with patch("services.cae.adapters.routal.httpx.AsyncClient") as Cls:
            ac = AsyncMock()
            ac.get = AsyncMock(return_value=FakeResp())
            Cls.return_value.__aenter__.return_value = ac
            adapter = RoutalAdapter(
                api_key="k", base_url="https://api.routal.com",
                project_ids=["p"])
            result = await adapter.list_recent_plans(
                created_from="2026-05-12T00:00:00Z")
        assert len(result) == 2
        assert {p["_id"] for p in result} == {"p2", "p3"}

    async def test_filters_by_range(self):
        plans_response = {
            "docs": [
                {"_id": "old",     "created_at": "2026-04-30T10:00:00Z"},
                {"_id": "inside1", "created_at": "2026-05-10T10:00:00Z"},
                {"_id": "inside2", "created_at": "2026-05-14T10:00:00Z"},
                {"_id": "future",  "created_at": "2026-06-01T10:00:00Z"},
            ]
        }

        class FakeResp:
            status_code = 200
            def json(self): return plans_response

        with patch("services.cae.adapters.routal.httpx.AsyncClient") as Cls:
            ac = AsyncMock()
            ac.get = AsyncMock(return_value=FakeResp())
            Cls.return_value.__aenter__.return_value = ac
            adapter = RoutalAdapter(
                api_key="k", base_url="https://api.routal.com",
                project_ids=["p"])
            result = await adapter.list_recent_plans(
                created_from="2026-05-01T00:00:00Z",
                created_to="2026-05-31T23:59:59Z")
        assert {p["_id"] for p in result} == {"inside1", "inside2"}

    async def test_no_filter_returns_all(self):
        plans_response = {"docs": [{"_id": "x"}, {"_id": "y"}]}

        class FakeResp:
            status_code = 200
            def json(self): return plans_response

        with patch("services.cae.adapters.routal.httpx.AsyncClient") as Cls:
            ac = AsyncMock()
            ac.get = AsyncMock(return_value=FakeResp())
            Cls.return_value.__aenter__.return_value = ac
            adapter = RoutalAdapter(
                api_key="k", base_url="https://api.routal.com",
                project_ids=["p"])
            result = await adapter.list_recent_plans()
        assert len(result) == 2


# ─────────────────── IngestService._pull_range ─────────────────────────
@pytest.mark.asyncio
class TestPullRange:
    async def test_pull_range_processes_stops(self, db, env):
        svc = IngestService(tenant_id=env["tenant_id"])
        plans = [{"_id": "plan-A", "created_at": "2026-05-14T10:00:00Z"}]
        stops = [
            {"_id": "stop-1", "external_id": "TRK-RA-1",
             "status": "en_route", "updated_at": "2026-05-14T11:00:00Z"},
            {"_id": "stop-2", "external_id": "TRK-RA-2",
             "status": "delivered", "updated_at": "2026-05-14T12:00:00Z"},
        ]
        # Mock platform creds
        with patch("repositories.platform_carriers.PlatformCarrierRepository.get_decrypted",
                   new=AsyncMock(return_value={
                       "api_key": "k", "base_url": "https://api.routal.com",
                       "project_ids": ["proj-1"]})):
            with patch("services.cae.adapters.routal.RoutalAdapter.list_recent_plans",
                       new=AsyncMock(return_value=plans)):
                with patch("services.cae.adapters.routal.RoutalAdapter.list_stops_in_plan",
                           new=AsyncMock(return_value=stops)):
                    res = await svc.trigger_pull(
                        client_id=env["client_id"],
                        date_from="2026-05-14",
                        date_to="2026-05-14",
                    )
        assert res["result"] == "pull_range_completed"
        assert res["summary"]["plans"] == 1
        assert res["summary"]["stops_seen"] == 2
        assert res["summary"]["guias_processed"] == 2

        # Guías creadas en BD
        count = await db.guias.count_documents({
            "tenant_id": env["tenant_id"],
            "tracking_id": {"$in": ["TRK-RA-1", "TRK-RA-2"]},
        })
        assert count == 2

    async def test_pull_range_idempotent(self, db, env):
        svc = IngestService(tenant_id=env["tenant_id"])
        plans = [{"_id": "p", "created_at": "2026-05-14T10:00:00Z"}]
        stops = [{"_id": "s", "external_id": "TRK-IDEM",
                  "status": "en_route", "updated_at": "2026-05-14T11:00:00Z"}]
        with patch("repositories.platform_carriers.PlatformCarrierRepository.get_decrypted",
                   new=AsyncMock(return_value={
                       "api_key": "k", "base_url": "x",
                       "project_ids": ["proj-1"]})):
            with patch("services.cae.adapters.routal.RoutalAdapter.list_recent_plans",
                       new=AsyncMock(return_value=plans)):
                with patch("services.cae.adapters.routal.RoutalAdapter.list_stops_in_plan",
                           new=AsyncMock(return_value=stops)):
                    await svc.trigger_pull(
                        client_id=env["client_id"],
                        date_from="2026-05-14", date_to="2026-05-14")
                    # 2do pull
                    await svc.trigger_pull(
                        client_id=env["client_id"],
                        date_from="2026-05-14", date_to="2026-05-14")
        # Solo 1 guía aunque hubo 2 pulls (idempotente por tracking_id)
        count = await db.guias.count_documents({
            "tenant_id": env["tenant_id"], "tracking_id": "TRK-IDEM",
        })
        assert count == 1

    async def test_unsupported_carrier_returns_message(self, db, env):
        # Cambiar carrier a fedex Y quitar `routal` legacy config
        await db.clients.update_one(
            {"id": env["client_id"]},
            {"$set": {"carrier": "fedex"},
             "$unset": {"routal": "", "carriers": ""}})
        svc = IngestService(tenant_id=env["tenant_id"])
        res = await svc.trigger_pull(
            client_id=env["client_id"],
            date_from="2026-05-14", date_to="2026-05-14")
        assert res["result"] == "unsupported_carrier"

    async def test_no_credentials_returns_message(self, db, env):
        svc = IngestService(tenant_id=env["tenant_id"])
        with patch("repositories.platform_carriers.PlatformCarrierRepository.get_decrypted",
                   new=AsyncMock(return_value=None)):
            res = await svc.trigger_pull(
                client_id=env["client_id"],
                date_from="2026-05-14", date_to="2026-05-14")
        assert res["result"] == "no_credentials"

    async def test_legacy_ping_without_range(self, db, env):
        """Sin date_from/date_to mantiene el comportamiento legacy."""
        svc = IngestService(tenant_id=env["tenant_id"])
        res = await svc.trigger_pull(client_id=env["client_id"])
        assert res["result"] == "pull_attempt_logged"


# ─────────────────── Endpoint REST ─────────────────────────
@pytest.mark.asyncio
class TestPullEndpoint:
    async def test_endpoint_accepts_date_range_body(self, db, env, http_client):
        headers = _bearer(user_id=env["superadmin_id"],
                          tenant_id=env["tenant_id"])
        with patch("repositories.platform_carriers.PlatformCarrierRepository.get_decrypted",
                   new=AsyncMock(return_value={
                       "api_key": "k", "base_url": "x",
                       "project_ids": ["proj-1"]})):
            with patch("services.cae.adapters.routal.RoutalAdapter.list_recent_plans",
                       new=AsyncMock(return_value=[])):
                r = await http_client.post(
                    f"/api/admin/ingest/pull/{env['client_id']}",
                    headers=headers,
                    json={"date_from": "2026-05-01", "date_to": "2026-05-14"},
                )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["result"] == "pull_range_completed"
        assert data["date_from"] == "2026-05-01"
        assert data["date_to"] == "2026-05-14"

    async def test_endpoint_without_body_does_ping(self, env, http_client):
        headers = _bearer(user_id=env["superadmin_id"],
                          tenant_id=env["tenant_id"])
        r = await http_client.post(
            f"/api/admin/ingest/pull/{env['client_id']}", headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["result"] == "pull_attempt_logged"

    async def test_endpoint_non_admin_forbidden(self, db, env, http_client):
        # Agent no puede llamar al endpoint
        ag_id = new_id()
        await db.users.insert_one({
            "id": ag_id, "tenant_id": env["tenant_id"],
            "email": "ag@t-56.io", "role": "agent",
            "password_hash": "x", "status": "active",
        })
        headers = _bearer(user_id=ag_id, tenant_id=env["tenant_id"],
                          role="agent")
        r = await http_client.post(
            f"/api/admin/ingest/pull/{env['client_id']}", headers=headers,
            json={"date_from": "2026-05-01", "date_to": "2026-05-14"})
        assert r.status_code == 403
