"""Tests P2 — benchmark + audit export firmado (PROMPT 26)."""
from __future__ import annotations
import csv
import hashlib
import hmac
import io
import os

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id
from repositories.ai import AIInvocationLogRepository
from seeds.ai_catalog import run as seed_ai
from services.ai import audit_export, benchmark


def _bearer(*, user_id, tenant_id, role="superadmin"):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_id, tenant_id=tenant_id, role=role, email='u@t')}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def p2_setup(db):
    await seed_ai()
    tid = new_id()
    uid = new_id()
    uid_admin = new_id()
    cl_id = new_id()
    await db.tenants.insert_one({"id": tid, "slug": "p2", "name": "P2",
                                 "status": "active"})
    await db.users.insert_many([
        {"id": uid, "tenant_id": tid, "email": "p2@t",
         "role": "superadmin", "status": "active"},
        {"id": uid_admin, "tenant_id": tid, "email": "p2admin@t",
         "role": "admin", "status": "active"},
    ])
    await db.clients.insert_one({"id": cl_id, "tenant_id": tid, "name": "ClP2"})
    return {"tenant_id": tid, "user_id": uid, "admin_user_id": uid_admin,
            "client_id": cl_id}


# ════════════════════════ Benchmark ══════════════════════════════════════
class TestBenchmark:
    async def test_dry_run_returns_estimates_for_all_models(self, p2_setup, db):
        doc = await benchmark.run_benchmark(dry_run=True, samples=1,
                                            triggered_by=p2_setup["user_id"])
        assert doc["mode"] == "dry_run"
        assert len(doc["results"]) == 4   # haiku, sonnet, gpt-4o-mini, gpt-4.1-mini
        for r in doc["results"]:
            assert r["mode"] == "dry_run"
            assert r["avg_cost_usd"] > 0
            assert r["p50_latency_ms"] is None  # dry run no mide latencia real
            assert r["model"] and r["provider"]
        # Persistido en ai_benchmarks
        count = await db.ai_benchmarks.count_documents({"id": doc["id"]})
        assert count == 1

    async def test_endpoint_run_dry_run(self, p2_setup, http_client):
        headers = _bearer(user_id=p2_setup["user_id"],
                          tenant_id=p2_setup["tenant_id"], role="superadmin")
        r = await http_client.post(
            "/api/admin/ai/benchmark/run?dry_run=true&samples=1",
            headers=headers,
        )
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["mode"] == "dry_run"
        assert len(d["results"]) >= 2

    async def test_endpoint_admin_forbidden(self, p2_setup, http_client):
        headers = _bearer(user_id=p2_setup["admin_user_id"],
                          tenant_id=p2_setup["tenant_id"], role="admin")
        r = await http_client.post(
            "/api/admin/ai/benchmark/run?dry_run=true",
            headers=headers,
        )
        assert r.status_code in (401, 403)

    async def test_list_benchmarks(self, p2_setup, http_client):
        # Pre-seed
        await benchmark.run_benchmark(dry_run=True, samples=1,
                                      triggered_by=p2_setup["user_id"])
        headers = _bearer(user_id=p2_setup["user_id"],
                          tenant_id=p2_setup["tenant_id"], role="admin")
        r = await http_client.get("/api/admin/ai/benchmark", headers=headers)
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) >= 1
        assert items[0]["mode"] in ("dry_run", "live")


# ════════════════════════ Audit Export ═══════════════════════════════════
class TestAuditExport:
    async def test_csv_signature_validates(self, p2_setup, monkeypatch):
        """El CSV debe poder verificarse con HMAC SHA-256 sobre el body."""
        # Insertar 2 invocaciones de prueba
        log_repo = AIInvocationLogRepository(tenant_id=p2_setup["tenant_id"])
        for i in range(2):
            await log_repo.append({
                "client_id": p2_setup["client_id"], "user_id": p2_setup["user_id"],
                "feature_id": "f", "feature_code": "classify_motivo",
                "ticket_id": None, "provider": "anthropic", "model": "haiku",
                "input_tokens": 100, "output_tokens": 5,
                "cost_usd": 0.001, "cost_mxn": 0.018, "exchange_rate": 17.5,
                "latency_ms": 50, "prompt_hash": f"h{i}",
                "prompt_masked_preview": "p", "response_hash": "r",
                "status": "success", "error_code": None, "request_id": new_id(),
            })

        secret = "test-audit-secret"
        monkeypatch.setenv("AUDIT_SIGNING_SECRET", secret)
        body, meta = await audit_export.build_csv(tenant_id=p2_setup["tenant_id"])
        assert meta["rows"] == 2

        # Verificar firma manualmente
        expected = "sha256=" + hmac.new(
            secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        assert meta["signature"] == expected

        # Header presente, columnas correctas
        text = body.decode("utf-8")
        reader = csv.reader(io.StringIO(text))
        header = next(reader)
        assert header[0] == "invocation_id"
        assert header[-1] == "request_id"
        assert "feature_code" in header
        rows = list(reader)
        assert len(rows) == 2

    async def test_csv_filters_by_date_and_status(self, p2_setup, monkeypatch):
        log_repo = AIInvocationLogRepository(tenant_id=p2_setup["tenant_id"])
        await log_repo.append({
            "client_id": p2_setup["client_id"], "user_id": None,
            "feature_id": "f", "feature_code": "classify_motivo",
            "ticket_id": None, "provider": "anthropic", "model": "haiku",
            "input_tokens": 100, "output_tokens": 5,
            "cost_usd": 0.001, "cost_mxn": 0, "exchange_rate": 17.5,
            "latency_ms": 50, "prompt_hash": "h",
            "prompt_masked_preview": "p", "response_hash": "r",
            "status": "success", "error_code": None, "request_id": new_id(),
        })
        await log_repo.append({
            "client_id": p2_setup["client_id"], "user_id": None,
            "feature_id": "f", "feature_code": "classify_motivo",
            "ticket_id": None, "provider": "anthropic", "model": "haiku",
            "input_tokens": 0, "output_tokens": 0,
            "cost_usd": 0, "cost_mxn": 0, "exchange_rate": 17.5,
            "latency_ms": 0, "prompt_hash": "",
            "prompt_masked_preview": "", "response_hash": "",
            "status": "capped", "error_code": "AI_BUDGET_CAPPED",
            "request_id": new_id(),
        })
        # filter status=success → sólo 1
        body, meta = await audit_export.build_csv(
            tenant_id=p2_setup["tenant_id"], status="success",
        )
        assert meta["rows"] == 1

    async def test_endpoint_csv_download(self, p2_setup, http_client, monkeypatch):
        log_repo = AIInvocationLogRepository(tenant_id=p2_setup["tenant_id"])
        await log_repo.append({
            "client_id": p2_setup["client_id"], "user_id": None,
            "feature_id": "f", "feature_code": "classify_motivo",
            "ticket_id": None, "provider": "anthropic", "model": "haiku",
            "input_tokens": 100, "output_tokens": 5,
            "cost_usd": 0.001, "cost_mxn": 0, "exchange_rate": 17.5,
            "latency_ms": 50, "prompt_hash": "h",
            "prompt_masked_preview": "p", "response_hash": "r",
            "status": "success", "error_code": None, "request_id": new_id(),
        })
        headers = _bearer(user_id=p2_setup["user_id"],
                          tenant_id=p2_setup["tenant_id"], role="superadmin")
        r = await http_client.get("/api/admin/ai/audit/export.csv", headers=headers)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert "X-MyE-Audit-Signature" in r.headers
        assert r.headers["X-MyE-Audit-Signature"].startswith("sha256=")
        assert int(r.headers["X-MyE-Audit-Rows"]) >= 1
        assert "attachment; filename=" in r.headers.get("content-disposition", "")

    async def test_endpoint_admin_forbidden(self, p2_setup, http_client):
        headers = _bearer(user_id=p2_setup["admin_user_id"],
                          tenant_id=p2_setup["tenant_id"], role="admin")
        r = await http_client.get("/api/admin/ai/audit/export.csv", headers=headers)
        assert r.status_code in (401, 403)

    async def test_endpoint_preview_returns_signature_and_sample(
        self, p2_setup, http_client,
    ):
        headers = _bearer(user_id=p2_setup["user_id"],
                          tenant_id=p2_setup["tenant_id"], role="superadmin")
        r = await http_client.get("/api/admin/ai/audit/preview", headers=headers)
        assert r.status_code == 200
        d = r.json()["data"]
        assert "signature" in d
        assert d["signature"].startswith("sha256=")
        assert "preview_csv" in d
        assert d["preview_csv"].startswith("invocation_id,")
