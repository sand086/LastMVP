"""Tests para 3 features finales del batch (Iter 15):
  - Email templates CRUD + preview con sustitución de variables
  - Cost-per-feature trend endpoint
  - Demo claims seed endpoint
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id


def _bearer(*, user_id: str, tenant_id: str, role: str = "admin",
            email: str = "x@t"):
    tok = create_access_function(user_id, tenant_id, role, email) if False else \
        create_access_token(user_id=user_id, tenant_id=tenant_id, role=role, email=email)
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def env(db):
    tid = new_id()
    root_uid = new_id()
    admin_uid = new_id()
    agent_uid = new_id()
    await db.tenants.insert_one({"id": tid, "slug": "tpl-iter15", "name": "T",
                                 "status": "active"})
    await db.users.insert_many([
        {"id": root_uid, "tenant_id": tid, "email": "root@t",
         "role": "root_dev", "status": "active"},
        {"id": admin_uid, "tenant_id": tid, "email": "ad@t",
         "role": "admin", "status": "active"},
        {"id": agent_uid, "tenant_id": tid, "email": "ag@t",
         "role": "agent", "status": "active"},
    ])
    return {"tenant_id": tid, "root_id": root_uid,
            "admin_id": admin_uid, "agent_id": agent_uid}


# ════════════════════════ Email templates ═══════════════════════════════
class TestEmailTemplates:
    async def test_list_empty(self, env, http_client):
        h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"])
        r = await http_client.get("/api/admin/email-templates", headers=h)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["count"] == 0
        assert "incident_notice" in d["supported_keys"]
        assert "test_email" in d["supported_keys"]

    async def test_upsert_then_list(self, env, http_client):
        h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"])
        r = await http_client.put("/api/admin/email-templates", headers=h, json={
            "key": "incident_notice",
            "subject": "[MyE] {{tracking_id}}",
            "html_body": "<p>Hola {{recipient_name}}, {{message}}</p>",
            "text_body": "Hola {{recipient_name}}",
        })
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["key"] == "incident_notice"
        # idempotente: upsert otra vez sobre la misma key
        r = await http_client.put("/api/admin/email-templates", headers=h, json={
            "key": "incident_notice",
            "subject": "v2",
            "html_body": "<p>v2</p>",
            "text_body": "",
        })
        assert r.status_code == 200
        # list cuenta sólo 1 (upsert)
        r = await http_client.get("/api/admin/email-templates", headers=h)
        assert r.json()["data"]["count"] == 1
        assert r.json()["data"]["items"][0]["subject"] == "v2"

    async def test_upsert_invalid_key(self, env, http_client):
        h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"])
        r = await http_client.put("/api/admin/email-templates", headers=h, json={
            "key": "no_existe",
            "subject": "x", "html_body": "<p>x</p>",
        })
        assert r.status_code == 422  # fail(VALIDATION_FAILED) → 422
        assert r.json()["success"] is False
        assert r.json()["errors"][0]["code"] == "VALIDATION_FAILED"

    async def test_preview_substitutes_variables(self, env, http_client):
        h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"])
        r = await http_client.post("/api/admin/email-templates/preview", headers=h,
                                    json={
            "subject": "Hola {{recipient_name}}",
            "html_body": "<p>{{message}}</p>",
            "text_body": "{{message}}",
        })
        assert r.status_code == 200
        d = r.json()["data"]
        assert "María García" in d["subject"]
        assert "retraso" in d["html"].lower() or "retraso" in d["text"].lower()

    async def test_delete_template(self, env, http_client):
        h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"])
        # Crear
        await http_client.put("/api/admin/email-templates", headers=h, json={
            "key": "test_email", "subject": "x", "html_body": "<p>x</p>",
        })
        # Delete
        r = await http_client.delete("/api/admin/email-templates/test_email", headers=h)
        assert r.status_code == 200
        assert r.json()["data"]["deleted"] is True
        # Delete inexistente → 404
        r = await http_client.delete("/api/admin/email-templates/test_email", headers=h)
        assert r.status_code == 404

    async def test_agent_forbidden(self, env, http_client):
        h = _bearer(user_id=env["agent_id"], tenant_id=env["tenant_id"], role="agent")
        r = await http_client.get("/api/admin/email-templates", headers=h)
        assert r.status_code == 403


# ════════════════════════ Cost trend ═══════════════════════════════════
class TestCostTrend:
    async def test_returns_empty_structure_with_no_data(self, env, http_client):
        h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"])
        r = await http_client.get("/api/admin/ai/cost-trend?days=30", headers=h)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["days"] == 30
        assert d["series"] == []
        assert d["totals_by_day"] == []
        assert d["grand_total_usd"] == 0.0
        assert d["features_count"] == 0

    async def test_aggregates_invocation_log(self, env, http_client, db):
        from datetime import datetime, timezone, timedelta
        tid = env["tenant_id"]
        now = datetime.now(timezone.utc)
        # 2 invocaciones hoy en classify_motivo + 1 ayer en summarize
        await db.ai_invocation_log.insert_many([
            {"id": new_id(), "tenant_id": tid, "feature_code": "classify_motivo",
             "client_id": "c1", "cost_usd": 0.01,
             "status": "success",
             "created_at": now.isoformat()},
            {"id": new_id(), "tenant_id": tid, "feature_code": "classify_motivo",
             "client_id": "c1", "cost_usd": 0.02,
             "status": "success",
             "created_at": now.isoformat()},
            {"id": new_id(), "tenant_id": tid, "feature_code": "summarize_timeline",
             "client_id": "c2", "cost_usd": 0.005,
             "status": "success",
             "created_at": (now - timedelta(days=1)).isoformat()},
            # Error → excluido
            {"id": new_id(), "tenant_id": tid, "feature_code": "classify_motivo",
             "client_id": "c1", "cost_usd": 99.0,
             "status": "error",
             "created_at": now.isoformat()},
            # Otro tenant → excluido
            {"id": new_id(), "tenant_id": "other", "feature_code": "classify_motivo",
             "client_id": "c1", "cost_usd": 50.0,
             "status": "success",
             "created_at": now.isoformat()},
        ])
        h = _bearer(user_id=env["admin_id"], tenant_id=tid)
        r = await http_client.get("/api/admin/ai/cost-trend?days=7", headers=h)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["features_count"] == 2
        assert d["grand_total_usd"] == 0.035
        # classify_motivo debe ir primero (gasto > summarize)
        assert d["series"][0]["feature_code"] == "classify_motivo"
        assert d["series"][0]["total_cost_usd"] == 0.03
        assert d["series"][0]["total_invocations"] == 2

    async def test_filter_by_client(self, env, http_client, db):
        from datetime import datetime, timezone
        tid = env["tenant_id"]
        now = datetime.now(timezone.utc).isoformat()
        await db.ai_invocation_log.insert_many([
            {"id": new_id(), "tenant_id": tid, "feature_code": "f1",
             "client_id": "cA", "cost_usd": 1.0, "status": "success",
             "created_at": now},
            {"id": new_id(), "tenant_id": tid, "feature_code": "f1",
             "client_id": "cB", "cost_usd": 2.0, "status": "success",
             "created_at": now},
        ])
        h = _bearer(user_id=env["admin_id"], tenant_id=tid)
        r = await http_client.get("/api/admin/ai/cost-trend?days=7&client_id=cA",
                                   headers=h)
        d = r.json()["data"]
        assert d["grand_total_usd"] == 1.0


# ════════════════════════ Demo claims seed ═════════════════════════════
class TestDemoClaimsSeed:
    async def test_seeds_3_claims_idempotent(self, env, http_client, db):
        # tenant slug del env fixture = "tpl-iter15"
        h = _bearer(user_id=env["root_id"], tenant_id=env["tenant_id"],
                    role="root_dev")
        r = await http_client.post("/api/admin/seed/demo-claims", headers=h)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["created"] == 3
        # Re-ejecutar: idempotente
        r = await http_client.post("/api/admin/seed/demo-claims", headers=h)
        d = r.json()["data"]
        assert d["created"] == 0
        assert d["skipped"] == 3
        # Verificar estados
        claims = await db.claims.find(
            {"tenant_id": env["tenant_id"], "seed_marker": "demo_claim_v1"},
            {"_id": 0, "estado": 1},
        ).to_list(length=10)
        estados = sorted([c["estado"] for c in claims])
        assert estados == ["conciliado", "en_dictamen_carrier",
                           "expediente_en_armado"]

    async def test_admin_forbidden(self, env, http_client):
        h = _bearer(user_id=env["admin_id"], tenant_id=env["tenant_id"],
                    role="admin")
        r = await http_client.post("/api/admin/seed/demo-claims", headers=h)
        assert r.status_code == 403
