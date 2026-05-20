"""PROMPT 26 V2 — Tests P1 del módulo Configuración IA.

Cubre:
  - CircuitBreaker  · abre tras N fallas, cooldown, half-open recovery
  - PromptCache     · hit/miss/TTL/cross-tenant aislado
  - Streaming SSE   · POST /api/ai/invoke/stream emite chunks + done
  - Approve/Webhook · POST /api/ai/invocations/{id}/approve dispara webhook
  - Daily summary   · _ai_section_metrics agrega correctamente
"""
from __future__ import annotations
import asyncio
import json
import time

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id
from repositories.ai import (
    AIBracketRepository, AIClientConfigRepository,
    AIInvocationLogRepository,
)
from seeds.ai_catalog import run as seed_ai
from services.ai import gateway as ai_gateway
from services.ai.circuit_breaker import CircuitBreaker, breaker as global_breaker
from services.ai.prompt_cache import _PromptCache, cache as global_cache
from services.daily_summary import _ai_section_metrics, render_summary_email


def _bearer(*, user_id, tenant_id, role="agent"):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_id, tenant_id=tenant_id, role=role, email='u@t')}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def ai_setup(db):
    await seed_ai()
    tid = new_id()
    uid = new_id()
    cl_id = new_id()
    await db.tenants.insert_one({"id": tid, "slug": "p1", "name": "P1", "status": "active"})
    await db.users.insert_one({"id": uid, "tenant_id": tid, "email": "p@p", "role": "agent", "status": "active"})
    await db.clients.insert_one({"id": cl_id, "tenant_id": tid, "name": "Cl P1"})
    bracket = await AIBracketRepository().by_name("starter")
    await AIClientConfigRepository(tenant_id=tid).upsert({
        "client_id": cl_id, "bracket_id": bracket["id"],
        "enabled_features": ["classify_motivo", "draft_response_to_client"],
        "is_active": True, "opt_in_signature": "Test",
    })
    return {"tenant_id": tid, "user_id": uid, "client_id": cl_id}


# ═══════════════════════ CircuitBreaker ══════════════════════════════════
class TestCircuitBreaker:
    async def test_closed_allows_calls(self):
        cb = CircuitBreaker()
        ok, _ = await cb.allow("test_provider")
        assert ok

    async def test_opens_after_threshold_failures(self, monkeypatch):
        # Bajar threshold para test rápido
        from services.ai import circuit_breaker as cbmod
        monkeypatch.setattr(cbmod, "_FAILURES", 3)
        cb = CircuitBreaker()
        for _ in range(3):
            await cb.record_failure("p1")
        ok, reason = await cb.allow("p1")
        assert ok is False
        assert reason and "breaker_open" in reason

    async def test_half_open_recovery_on_success(self, monkeypatch):
        from services.ai import circuit_breaker as cbmod
        monkeypatch.setattr(cbmod, "_FAILURES", 2)
        monkeypatch.setattr(cbmod, "_COOLDOWN_S", 0.05)
        cb = CircuitBreaker()
        await cb.record_failure("p2")
        await cb.record_failure("p2")
        # Ahora open
        assert (await cb.allow("p2"))[0] is False
        await asyncio.sleep(0.08)
        # Cooldown expiró → permite sonda
        ok, _ = await cb.allow("p2")
        assert ok is True
        # Si la sonda tiene éxito → CLOSED
        await cb.record_success("p2")
        ok2, _ = await cb.allow("p2")
        assert ok2 is True

    async def test_gateway_uses_breaker(self, ai_setup, monkeypatch):
        """Si el breaker está abierto, invoke devuelve AI_PROVIDER_UNAVAILABLE sin llamar al provider."""
        # Abrir el breaker para anthropic
        from services.ai import circuit_breaker as cbmod
        monkeypatch.setattr(cbmod, "_FAILURES", 1)
        monkeypatch.setattr(cbmod, "_COOLDOWN_S", 30)
        # Forzar 1 falla → abre
        await ai_gateway.breaker.record_failure("anthropic")
        called = {"hit": False}
        async def fake_call(*a, **k):
            called["hit"] = True
            return {"text": "x", "input_tokens": 1, "output_tokens": 1, "latency_ms": 1}
        monkeypatch.setattr(ai_gateway, "_call_provider", fake_call)
        monkeypatch.setenv("EMERGENT_LLM_KEY", "k")
        # Necesitamos limpiar el cache de classify_motivo (cache_enabled=True) para no servir desde cache
        await global_cache.clear()
        # summarize_timeline no tiene cache enabled, usémoslo. Pero no está enabled para este client.
        # Re-upsertear con summarize_timeline:
        bracket = await AIBracketRepository().by_name("starter")
        await AIClientConfigRepository(tenant_id=ai_setup["tenant_id"]).upsert({
            "client_id": ai_setup["client_id"], "bracket_id": bracket["id"],
            "enabled_features": ["summarize_timeline"],
            "is_active": True, "opt_in_signature": "T",
        })
        result = await ai_gateway.invoke(
            tenant_id=ai_setup["tenant_id"], client_id=ai_setup["client_id"],
            user_id=ai_setup["user_id"], feature_code="summarize_timeline",
            raw_input={"events": ["e1"]},
        )
        assert not result.ok
        assert result.code == "AI_PROVIDER_UNAVAILABLE"
        assert called["hit"] is False
        # Limpiar para no afectar otros tests
        await ai_gateway.breaker.record_success("anthropic")


# ═══════════════════════ PromptCache ═════════════════════════════════════
class TestPromptCache:
    async def test_hit_after_put(self):
        c = _PromptCache()
        await c.put("t1", "f", "m", "h", {"text": "hello", "input_tokens": 10, "output_tokens": 5, "latency_ms": 10})
        v = await c.get("t1", "f", "m", "h")
        assert v is not None
        assert v["text"] == "hello"

    async def test_cross_tenant_miss(self):
        c = _PromptCache()
        await c.put("tA", "f", "m", "h", {"text": "secret", "input_tokens": 1, "output_tokens": 1, "latency_ms": 1})
        v = await c.get("tB", "f", "m", "h")
        assert v is None

    async def test_ttl_expiry(self, monkeypatch):
        from services.ai import prompt_cache as pcmod
        monkeypatch.setattr(pcmod, "_TTL_S", 0.05)
        c = _PromptCache()
        await c.put("t", "f", "m", "h", {"text": "x", "input_tokens": 1, "output_tokens": 1, "latency_ms": 1})
        await asyncio.sleep(0.08)
        v = await c.get("t", "f", "m", "h")
        assert v is None

    async def test_gateway_serves_from_cache_on_second_call(self, ai_setup, monkeypatch):
        """Segunda invocación con mismo prompt → cache hit, NO llama provider, costo=0."""
        await global_cache.clear()
        calls = {"n": 0}
        async def fake_call(*a, **k):
            calls["n"] += 1
            return {"text": "EXTRAVIO", "input_tokens": 100, "output_tokens": 5, "latency_ms": 50}
        monkeypatch.setattr(ai_gateway, "_call_provider", fake_call)
        monkeypatch.setenv("EMERGENT_LLM_KEY", "k")
        # classify_motivo tiene cache_enabled=True
        r1 = await ai_gateway.invoke(
            tenant_id=ai_setup["tenant_id"], client_id=ai_setup["client_id"],
            user_id=ai_setup["user_id"], feature_code="classify_motivo",
            raw_input={"description": "El paquete nunca llegó"},
        )
        r2 = await ai_gateway.invoke(
            tenant_id=ai_setup["tenant_id"], client_id=ai_setup["client_id"],
            user_id=ai_setup["user_id"], feature_code="classify_motivo",
            raw_input={"description": "El paquete nunca llegó"},
        )
        assert r1.ok and r2.ok
        assert calls["n"] == 1, "Segunda llamada debe servirse desde cache"
        assert r2.data["from_cache"] is True
        assert r2.data["cost_estimate_usd"] == 0.0


# ═══════════════════════ Streaming SSE ═══════════════════════════════════
class TestStreamingSSE:
    async def test_invoke_stream_emits_chunks_and_done(self, ai_setup, monkeypatch, http_client):
        async def fake_call(*a, **k):
            return {"text": "Estimado cliente, hemos recibido tu solicitud.",
                    "input_tokens": 100, "output_tokens": 10, "latency_ms": 50}
        monkeypatch.setattr(ai_gateway, "_call_provider", fake_call)
        monkeypatch.setenv("EMERGENT_LLM_KEY", "k")
        await global_cache.clear()
        headers = _bearer(user_id=ai_setup["user_id"], tenant_id=ai_setup["tenant_id"])
        async with http_client.stream(
            "POST", "/api/ai/invoke/stream",
            json={"feature_code": "classify_motivo",
                  "input": {"client_id": ai_setup["client_id"], "description": "Ejemplo del stream"}},
            headers=headers,
        ) as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers.get("content-type", "")
            chunks = []
            done = None
            async for line in r.aiter_lines():
                if line.startswith("event: chunk"):
                    pass
                elif line.startswith("data: ") and "text" in line:
                    chunks.append(json.loads(line[6:]).get("text", ""))
                elif line.startswith("data: ") and "invocation_id" in line:
                    done = json.loads(line[6:])
            assert len(chunks) > 0
            assert done is not None
            assert "invocation_id" in done


# ═══════════════════════ Approve + Webhook ═══════════════════════════════
class TestApproveAndWebhook:
    async def test_approve_marks_invocation(self, ai_setup, monkeypatch, http_client):
        async def fake_call(*a, **k):
            return {"text": "Estimado <PER_1>", "input_tokens": 100, "output_tokens": 5, "latency_ms": 50}
        monkeypatch.setattr(ai_gateway, "_call_provider", fake_call)
        monkeypatch.setenv("EMERGENT_LLM_KEY", "k")
        await global_cache.clear()
        # Generar una invocación draft (client_final feature)
        result = await ai_gateway.invoke(
            tenant_id=ai_setup["tenant_id"], client_id=ai_setup["client_id"],
            user_id=ai_setup["user_id"], feature_code="draft_response_to_client",
            raw_input={"context": "Test"},
        )
        assert result.ok
        inv_id = result.data["invocation_id"]
        # Aprobar
        headers = _bearer(user_id=ai_setup["user_id"], tenant_id=ai_setup["tenant_id"])
        r = await http_client.post(f"/api/ai/invocations/{inv_id}/approve", headers=headers)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["invocation_id"] == inv_id
        assert d["approved_at"]

    async def test_approve_double_blocks(self, ai_setup, monkeypatch, http_client):
        async def fake_call(*a, **k):
            return {"text": "ok", "input_tokens": 1, "output_tokens": 1, "latency_ms": 1}
        monkeypatch.setattr(ai_gateway, "_call_provider", fake_call)
        monkeypatch.setenv("EMERGENT_LLM_KEY", "k")
        await global_cache.clear()
        result = await ai_gateway.invoke(
            tenant_id=ai_setup["tenant_id"], client_id=ai_setup["client_id"],
            user_id=ai_setup["user_id"], feature_code="draft_response_to_client",
            raw_input={"context": "T"},
        )
        inv_id = result.data["invocation_id"]
        headers = _bearer(user_id=ai_setup["user_id"], tenant_id=ai_setup["tenant_id"])
        r1 = await http_client.post(f"/api/ai/invocations/{inv_id}/approve", headers=headers)
        assert r1.status_code == 200
        r2 = await http_client.post(f"/api/ai/invocations/{inv_id}/approve", headers=headers)
        assert r2.status_code == 422
        assert r2.json()["errors"][0]["code"] == "VALIDATION_FAILED"

    async def test_webhook_outbound_signature_and_marking(self, ai_setup, db, monkeypatch):
        """Configura un webhook URL+secret y verifica firma HMAC SHA-256 + marcado en log."""
        # Configurar webhook en client config
        await AIClientConfigRepository(tenant_id=ai_setup["tenant_id"]).upsert({
            "client_id": ai_setup["client_id"],
            "webhook_outbound_url": "https://example.test/hook",
            "webhook_outbound_secret": "shh",
        })
        # Mockear httpx.AsyncClient.post
        import services.ai.webhook_out as wo
        captured = {}
        class _FakeResp:
            status_code = 200
        class _FakeClient:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return None
            async def post(self, url, content, headers):
                captured["url"] = url
                captured["sig"] = headers.get("X-MyE-Signature")
                captured["body"] = content
                return _FakeResp()
        monkeypatch.setattr(wo.httpx, "AsyncClient", lambda **kw: _FakeClient())

        # Insertar manualmente una invocación draft aprobable
        log_repo = AIInvocationLogRepository(tenant_id=ai_setup["tenant_id"])
        inv = await log_repo.append({
            "client_id": ai_setup["client_id"], "user_id": ai_setup["user_id"],
            "feature_id": "f1", "feature_code": "draft_response_to_client",
            "ticket_id": None, "provider": "anthropic", "model": "claude-sonnet",
            "input_tokens": 100, "output_tokens": 5,
            "cost_usd": 0.001, "cost_mxn": 0.02, "exchange_rate": 17.5,
            "latency_ms": 50, "prompt_hash": "h1",
            "prompt_masked_preview": "x", "response_hash": "rh",
            "status": "success", "error_code": None, "request_id": "rq",
            "destinatario": "client_final", "approved_at": None, "approved_by": None,
            "webhook_delivered": None,
        })
        # Disparar deliver()
        result = await wo.deliver(
            tenant_id=ai_setup["tenant_id"], invocation_id=inv["id"],
            payload={"a": 1}, url="https://example.test/hook", secret="shh",
        )
        assert result["ok"] is True
        assert captured["url"] == "https://example.test/hook"
        assert captured["sig"] is not None and captured["sig"].startswith("sha256=")
        # log marcado
        updated = await db.ai_invocation_log.find_one({"id": inv["id"]}, {"_id": 0})
        assert updated["webhook_delivered"] is True
        assert updated["webhook_status_code"] == 200


# ═══════════════════════ Daily Summary AI section ════════════════════════
class TestDailySummaryAISection:
    async def test_metrics_aggregates_today_invocations(self, ai_setup, db):
        log_repo = AIInvocationLogRepository(tenant_id=ai_setup["tenant_id"])
        # 2 success, 1 cache_hit, 1 capped
        for status, cost in [("success", 0.01), ("success", 0.02), ("cache_hit", 0), ("capped", 0)]:
            await log_repo.append({
                "client_id": ai_setup["client_id"], "user_id": ai_setup["user_id"],
                "feature_id": "f", "feature_code": "classify_motivo",
                "ticket_id": None, "provider": "anthropic", "model": "claude-haiku",
                "input_tokens": 100, "output_tokens": 5,
                "cost_usd": cost, "cost_mxn": 0, "exchange_rate": 17.5,
                "latency_ms": 50, "prompt_hash": "h", "prompt_masked_preview": "p",
                "response_hash": "r", "status": status, "error_code": None,
                "request_id": new_id(),
            })
        ai_metrics = await _ai_section_metrics(ai_setup["tenant_id"])
        assert ai_metrics["invocations_today"] == 4
        assert ai_metrics["cost_usd_today"] == 0.03
        assert ai_metrics["cache_hits_today"] == 1
        assert ai_metrics["capped_today"] == 1
        assert ai_metrics["cache_hit_rate_pct"] == 25.0

    def test_render_summary_includes_ai_block_when_invocations(self):
        metrics = {
            "open_tickets": 1, "resolved_today": 0, "backlog_aged_24h": 0,
            "automations_today": 0, "sla_breaches_today": 0,
            "agents_inactive_today": 0, "claims_dictamen_aging": 0,
            "ai": {"invocations_today": 5, "cost_usd_today": 0.05,
                   "cache_hits_today": 2, "cache_hit_rate_pct": 40.0,
                   "capped_today": 0, "errors_today": 0, "top_features_today": []},
        }
        html, text = render_summary_email(tenant_name="Test", metrics=metrics)
        assert "IA · módulo de configuración" in html
        assert "Invocaciones IA" in html
        assert "$0.0500" in html
        assert "40.0%" in html

    def test_render_summary_omits_ai_block_when_zero(self):
        metrics = {
            "open_tickets": 1, "resolved_today": 0, "backlog_aged_24h": 0,
            "automations_today": 0, "sla_breaches_today": 0,
            "agents_inactive_today": 0, "claims_dictamen_aging": 0,
            "ai": {"invocations_today": 0, "cost_usd_today": 0,
                   "cache_hits_today": 0, "cache_hit_rate_pct": 0,
                   "capped_today": 0, "errors_today": 0, "top_features_today": []},
        }
        html, text = render_summary_email(tenant_name="Test", metrics=metrics)
        assert "IA · módulo de configuración" not in html
